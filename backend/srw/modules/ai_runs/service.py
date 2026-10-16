from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.clock import utc_now
from srw.modules.ai_runs.models import AiRun


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def _hash_payload(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return _sha256_text(raw)


def start_ai_run(
    session: Session,
    *,
    task_type: str,
    project_id: str = "",
    candidate_id: str = "",
    source_id: str = "",
    provider_kind: str = "",
    model_name: str = "",
    prompt_version: str = "evidence.claims.v1",
    schema_version: str = "claim-proposals.v1",
    input_material: str = "",
    input_safety_meta: dict[str, Any] | None = None,
    retry_count: int = 0,
) -> AiRun:
    row = AiRun(
        task_type=task_type.strip() or "unknown",
        project_id=project_id or "",
        candidate_id=candidate_id or "",
        source_id=source_id or "",
        provider_kind=provider_kind or "",
        model_name=model_name or "",
        prompt_version=prompt_version or "",
        schema_version=schema_version or "",
        input_hash=_sha256_text(input_material),
        input_safety_meta_json=json.dumps(input_safety_meta or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        status="running",
        retry_count=max(0, int(retry_count)),
    )
    session.add(row)
    session.flush()
    return row


def finish_ai_run(session: Session, run_id: str, payload: Any, *, latency_ms: int) -> AiRun:
    row = session.get(AiRun, run_id)
    if row is None:
        raise LookupError(run_id)
    row.status = "succeeded"
    row.output_hash = _hash_payload(payload)
    row.latency_ms = max(0, int(latency_ms))
    row.finished_at = utc_now()
    session.flush()
    return row


def fail_ai_run(
    session: Session,
    run_id: str,
    exc: BaseException,
    *,
    latency_ms: int,
    error_code: str = "",
    status: str = "failed",
) -> AiRun:
    row = session.get(AiRun, run_id)
    if row is None:
        raise LookupError(run_id)
    row.status = status
    row.error_class = type(exc).__name__[:80]
    row.error_code = str(error_code or getattr(exc, "code", "") or "")[:80]
    row.latency_ms = max(0, int(latency_ms))
    row.finished_at = utc_now()
    session.flush()
    return row


def list_ai_runs(
    session: Session,
    *,
    project_id: str = "",
    candidate_id: str = "",
    source_id: str = "",
    status: str = "",
    limit: int = 100,
) -> list[AiRun]:
    stmt = select(AiRun)
    if project_id:
        stmt = stmt.where(AiRun.project_id == project_id)
    if candidate_id:
        stmt = stmt.where(AiRun.candidate_id == candidate_id)
    if source_id:
        stmt = stmt.where(AiRun.source_id == source_id)
    if status:
        stmt = stmt.where(AiRun.status == status)
    return list(session.scalars(stmt.order_by(AiRun.started_at.desc(), AiRun.id.desc()).limit(min(max(int(limit), 1), 500))))
