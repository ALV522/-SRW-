"""Experimental E3 **transactional** Action Plan CAS inside a disposable C11 Core.

No production backend edits. A new Starlette route is installed at application
startup ONLY by the explicitly synthetic E3 server. Both revision metadata,
business mutation, and audit event commit in one SQLite transaction.

Unlike the E2 proxy lock, SQLite BEGIN IMMEDIATE serializes writes from
independent connections/processes participating in this E3 contract.
Legacy clients that bypass E3 can still write without bumping the E3 revision;
therefore this is a transaction proof, NOT a production migration.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from sqlalchemy import text, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.candidate.models import Candidate
from srw.modules.recruiting.operations_models import CandidateActionPlan
from srw.recruiting.workbench import (
    PRIORITIES, CONTACT_STATUSES, action_plan_view, upsert_action_plan
)

# Deliberately a distinct, experimental schema table. Never update production
# v1_0014 schema, and never add these routes to a normal C11 app.
REVISION_TABLE = "e3_synthetic_action_plan_revision"
TAG_RE = re.compile(r'^"e3-ap-v(0|[1-9][0-9]{0,17})"$')
ALLOWED_FIELDS = frozenset({
    "owner", "priority", "contact_status", "next_contact_at",
    "reason", "last_result",
})
MAX_BODY_SIZE = 8192


class RevisionConflict(Exception):
    def __init__(self, revision: int):
        self.revision = revision


class AtomicActionPlan:
    def __init__(self, engine: Engine, *, synthetic_only: bool = True):
        if not synthetic_only or engine.dialect.name != "sqlite":
            raise ValueError("E3 requires a disposable local SQLite workspace")
        self.engine = engine
        with engine.begin() as conn:
            conn.exec_driver_sql(
                f"CREATE TABLE IF NOT EXISTS {REVISION_TABLE} ("
                "candidate_id TEXT PRIMARY KEY NOT NULL,"
                "revision INTEGER NOT NULL CHECK (revision >= 1))"
            )

    @staticmethod
    def tag(revision: int) -> str:
        return f'"e3-ap-v{revision}"'

    def _revision(self, session: Session, candidate_id: str) -> int:
        value = session.execute(
            text(f"SELECT revision FROM {REVISION_TABLE} WHERE candidate_id=:id"),
            {"id":candidate_id}
        ).scalar_one_or_none()
        return int(value) if value is not None else 0

    @staticmethod
    def _view(session: Session, candidate_id: str) -> dict[str, Any]:
        candidate = session.get(Candidate, candidate_id)
        if candidate is None:
            raise V1NotFoundError(f"candidate not found: {candidate_id}")
        row = session.scalar(
            select(CandidateActionPlan).where(
                CandidateActionPlan.candidate_id == candidate_id
            )
        )
        if row is not None:
            return action_plan_view(row)
        return {
            "candidate_id": candidate_id,
            "project_id": candidate.project_id,
            "priority": "normal",
            "owner": "",
            "contact_status": "to_contact",
            "next_contact_at": None,
            "reason": "",
            "last_result": "",
        }

    def read(self, candidate_id: str) -> tuple[dict[str, Any], int]:
        with Session(self.engine, autoflush=False) as session:
            plan = self._view(session, candidate_id)
            return plan, self._revision(session, candidate_id)

    def update(
        self, candidate_id: str, expected_revision: int,
        patch: dict[str, Any]
    ) -> tuple[dict[str, Any], int]:
        """One transaction: acquire write lock, compare, mutate+audit, increment."""
        if not isinstance(patch, dict) or not patch or set(patch)-ALLOWED_FIELDS:
            raise ValueError("E3 only accepts approved nonempty Action Plan fields")
        if any(
            not (isinstance(value, str) or (key == "next_contact_at" and value is None))
            for key, value in patch.items()
        ):
            raise ValueError("E3 Action Plan fields have invalid value types")
        if "priority" in patch and patch["priority"] not in PRIORITIES:
            raise ValueError("E3 invalid contact priority")
        if "contact_status" in patch and patch["contact_status"] not in CONTACT_STATUSES:
            raise ValueError("E3 invalid contact status")
        if any(len(value) > 1000 for key, value in patch.items() if isinstance(value, str)):
            raise ValueError("E3 field value exceeds 1000 characters")

        with self.engine.connect() as conn:
            # Lock is acquired *before* revision comparison; a second writer
            # blocks here until the first transaction commits or rolls back.
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                with Session(bind=conn, autoflush=False, expire_on_commit=False) as session:
                    current = self._revision(session, candidate_id)
                    if current != expected_revision:
                        # No business mutation or audit event has been executed.
                        raise RevisionConflict(current)
                    updated = upsert_action_plan(
                        session, candidate_id, {**patch, "actor":"human"}
                    )
                    session.flush()  # Includes C11 append_audit_event(...)
                    changed = action_plan_view(updated)
                    new_revision = current + 1
                    conn.execute(
                        text(
                            f"INSERT INTO {REVISION_TABLE} (candidate_id, revision) "
                            "VALUES (:id, :revision) "
                            "ON CONFLICT(candidate_id) DO UPDATE SET revision=excluded.revision"
                        ),
                        {"id":candidate_id, "revision":new_revision},
                    )
                    # Owns business write, audit insert and revision bump.
                    conn.commit()
                    return changed, new_revision
            except Exception:
                conn.rollback()
                raise


def install_e3_action_plan_route(app, engine: Engine) -> AtomicActionPlan:
    store = AtomicActionPlan(engine)

    async def action_plan(request: Request):
        cid = request.path_params["candidate_id"]
        if request.method == "GET":
            try:
                body, revision = store.read(cid)
            except V1NotFoundError:
                return JSONResponse({"error":"candidate not found"}, status_code=404)
            return JSONResponse(body, headers={"ETag":store.tag(revision), "Cache-Control":"no-store"})

        if request.headers.get("content-type","").split(";",1)[0].strip() != "application/json":
            return JSONResponse({"error":"application/json required"}, status_code=415)
        tag = request.headers.get("if-match", "")
        match = TAG_RE.fullmatch(tag)
        if match is None:
            return JSONResponse({"error":"E3 requires If-Match ETag from GET"}, status_code=428)
        raw = await request.body()
        if not raw or len(raw) > MAX_BODY_SIZE:
            return JSONResponse({"error":"invalid request size"}, status_code=413)
        try:
            import json
            patch = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return JSONResponse({"error":"invalid JSON"}, status_code=400)
        try:
            plan, revision = store.update(cid, int(match.group(1)), patch)
        except RevisionConflict as exc:
            return JSONResponse(
                {"error":"STALE_ACTION_PLAN",
                 "message":"Conflict detected in SQLite before business mutation; refresh.",
                 "current_revision":exc.revision},
                status_code=412, headers={"ETag":store.tag(exc.revision)}
            )
        except V1NotFoundError:
            return JSONResponse({"error":"candidate not found"}, status_code=404)
        except (ValueError, V1InvariantError) as exc:
            return JSONResponse({"error":str(exc)}, status_code=422)
        return JSONResponse(plan, headers={
            "ETag":store.tag(revision), "Cache-Control":"no-store"
        })

    # The real Starlette app and all business endpoints remain the same;
    # only this one synthetic route intercepts the existing action-plan route.
    app.router.routes.insert(
        0, Route("/api/v1/candidates/{candidate_id}/action-plan",
                 action_plan, methods=["GET","PATCH"])
    )
    return store
