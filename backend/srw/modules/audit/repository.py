from __future__ import annotations

from sqlalchemy.orm import Session

from srw.kernel.hashing import canonical_json_bytes
from srw.modules.audit.models import AuditEvent


def append_audit_event(
    session: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor: str,
    reason: str = "",
    before_hash: str | None = None,
    after_hash: str | None = None,
    payload: dict | None = None,
    project_id: str | None = None,
    candidate_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        candidate_id=candidate_id,
        actor=actor,
        reason=reason,
        before_hash=before_hash,
        after_hash=after_hash,
        payload_json=canonical_json_bytes(payload or {}).decode("utf-8"),
    )
    session.add(event)
    session.flush()
    return event
