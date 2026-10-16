from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from srw.kernel.clock import utc_now
from srw.kernel.hashing import canonical_json_bytes
from srw.kernel.ids import new_id
from srw.runtime.jobs.models import Job


class JobEngine:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        type: str,
        payload: dict,
        *,
        idempotency_key: str,
        priority: int = 100,
        resource_class: str = "io",
    ) -> Job:
        existing = self.session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
        row = Job(
            type=type,
            payload_json=canonical_json_bytes(payload).decode(),
            priority=priority,
            idempotency_key=idempotency_key,
            resource_class=resource_class,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def lease_next(
        self,
        worker_id: str,
        *,
        lease_for: timedelta = timedelta(minutes=5),
        resource_class: str | None = None,
    ) -> Job | None:
        now = utc_now()
        eligible = or_(
            Job.status == "queued",
            and_(Job.status == "running", Job.lease_until < now),
        )
        candidate = select(Job.id).where(eligible)
        if resource_class:
            candidate = candidate.where(Job.resource_class == resource_class)
        candidate = candidate.order_by(Job.priority, Job.created_at, Job.id).limit(1)

        lease_token = new_id()
        statement = (
            update(Job)
            .where(Job.id == candidate.scalar_subquery(), eligible)
            .values(
                status="running",
                worker_id=worker_id,
                lease_token=lease_token,
                lease_until=now + lease_for,
                started_at=func.coalesce(Job.started_at, now),
                attempt=Job.attempt + 1,
                finished_at=None,
            )
            .returning(Job.id)
            .execution_options(synchronize_session=False)
        )
        claimed_id = self.session.scalar(statement)
        if claimed_id is None:
            return None
        self.session.expire_all()
        return self.session.get(Job, claimed_id)


    def cancel(self, job_id: str) -> bool:
        now = utc_now()
        result = self.session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_(("queued", "running", "failed")))
            .values(status="cancelled", finished_at=now, lease_until=None, lease_token=None)
            .execution_options(synchronize_session=False)
        )
        self.session.expire_all()
        return result.rowcount == 1

    def requeue(self, job_id: str) -> bool:
        result = self.session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_(("failed", "succeeded", "cancelled", "running", "queued")))
            .values(status="queued", worker_id=None, lease_until=None, lease_token=None, finished_at=None)
            .execution_options(synchronize_session=False)
        )
        self.session.expire_all()
        return result.rowcount == 1

    def is_owned(self, job_id: str, worker_id: str, lease_token: str | None) -> bool:
        if not lease_token:
            return False
        row = self.session.scalar(
            select(Job.id).where(
                Job.id == job_id, Job.worker_id == worker_id, Job.lease_token == lease_token,
                Job.status == "running", Job.lease_until >= utc_now(),
            )
        )
        return row is not None

    def succeed(self, job_id: str, worker_id: str, lease_token: str | None) -> Job:
        return self._finish(job_id, worker_id, lease_token, status="succeeded")

    def fail(self, job_id: str, worker_id: str, lease_token: str | None) -> Job:
        return self._finish(job_id, worker_id, lease_token, status="failed")

    def _finish(self, job_id: str, worker_id: str, lease_token: str | None, *, status: str) -> Job:
        if not lease_token:
            raise ValueError("job lease ownership mismatch")
        now = utc_now()
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.worker_id == worker_id,
                Job.lease_token == lease_token,
                Job.status == "running",
                Job.lease_until >= now,
            )
            .values(
                status=status,
                finished_at=now,
                lease_until=None,
                lease_token=None,
            )
            .execution_options(synchronize_session=False)
        )
        result = self.session.execute(statement)
        if result.rowcount != 1:
            raise ValueError("job lease ownership mismatch")
        self.session.expire_all()
        row = self.session.get(Job, job_id)
        if row is None:
            raise ValueError("job lease ownership mismatch")
        return row
