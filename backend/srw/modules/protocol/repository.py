from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import canonical_json_bytes, content_hash
from srw.kernel.ids import new_id
from srw.modules.protocol.models import Project, ProtocolRevision



def normalize_protocol_payload(payload: dict) -> dict:
    """Accept the UI-friendly protocol shape and persist one canonical contract."""
    if not isinstance(payload, dict):
        raise V1InvariantError("protocol payload must be an object")
    normalized = dict(payload)
    raw_criteria = payload.get("criteria") or []
    if not isinstance(raw_criteria, list):
        raise V1InvariantError("protocol criteria must be a list")
    criteria=[]
    for item in raw_criteria:
        if not isinstance(item, dict):
            raise V1InvariantError("criterion must be an object")
        row=dict(item)
        key=str(row.get("criterion_key") or row.get("key") or "").strip() or new_id()
        row.pop("key",None)
        row["criterion_key"]=key
        criteria.append(row)
    normalized["criteria"]=criteria
    known=[str(x.get("criterion_key") or "") for x in criteria]
    raw_stages=payload.get("assessment_stages") or []
    if not isinstance(raw_stages,list):
        raise V1InvariantError("assessment_stages must be a list")
    stages=[]
    for stage in raw_stages:
        if isinstance(stage,str):
            value=stage.strip()
            if value:
                stages.append({"stage_key":value,"name":value,"criteria":[]})
        elif isinstance(stage,dict):
            row=dict(stage)
            refs=row.get("criteria") or []
            if not isinstance(refs,list):
                raise V1InvariantError("assessment stage criteria must be a list")
            row["criteria"]=[str(x) for x in refs]
            stages.append(row)
        else:
            raise V1InvariantError("assessment stage must be an object or string")
    normalized["assessment_stages"]=stages
    return normalized

def validate_protocol_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise V1InvariantError("protocol payload must be an object")
    criteria = payload.get("criteria") or []
    if not isinstance(criteria, list):
        raise V1InvariantError("protocol criteria must be a list")
    keys: list[str] = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise V1InvariantError("criterion must be an object")
        key = str(criterion.get("criterion_key") or "").strip()
        if not key:
            raise V1InvariantError("criterion_key is required")
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise V1InvariantError("criterion_key must be unique within a protocol")
    known = set(keys)
    for stage in payload.get("assessment_stages") or []:
        if not isinstance(stage, dict):
            raise V1InvariantError("assessment stage must be an object")
        refs = stage.get("criteria") or []
        unknown = sorted({str(ref) for ref in refs} - known)
        if unknown:
            raise V1InvariantError(f"assessment stage references unknown criteria: {unknown}")


class ProtocolRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_draft(self, project_id: str, payload: dict, provenance: dict | None = None) -> ProtocolRevision:
        payload = normalize_protocol_payload(payload)
        validate_protocol_payload(payload)
        project = self.session.get(Project, project_id)
        if project is None:
            raise V1NotFoundError(f"project not found: {project_id}")
        next_revision = (
            self.session.scalar(
                select(func.coalesce(func.max(ProtocolRevision.revision), 0)).where(
                    ProtocolRevision.project_id == project_id
                )
            )
            or 0
        ) + 1
        row = ProtocolRevision(
            project_id=project_id,
            revision=next_revision,
            state="draft",
            payload_json=canonical_json_bytes(payload).decode("utf-8"),
            provenance_json=canonical_json_bytes(provenance or {}).decode("utf-8"),
            content_hash=content_hash(payload),
        )
        self.session.add(row)
        self.session.flush()
        return row



    def get_payload(self, revision_id: str) -> dict:
        return get_protocol_payload(self.session, revision_id)

    def fork_current_to_draft(self, project_id: str) -> ProtocolRevision:
        project = self.session.get(Project, project_id)
        if project is None:
            raise V1NotFoundError(f"project not found: {project_id}")
        existing = self.session.scalar(
            select(ProtocolRevision)
            .where(ProtocolRevision.project_id == project_id, ProtocolRevision.state == "draft")
            .order_by(ProtocolRevision.revision.desc())
            .limit(1)
        )
        if existing is not None:
            return existing
        if not project.current_protocol_revision_id:
            raise V1InvariantError("project has no published protocol to fork")
        current = self.session.get(ProtocolRevision, project.current_protocol_revision_id)
        if current is None or current.state != "published":
            raise V1InvariantError("current protocol pointer is invalid")
        payload = get_protocol_payload(self.session, current.id)
        return self.create_draft(
            project_id,
            payload,
            {"origin": "fork-current", "forked_from_revision_id": current.id},
        )

    def update_draft(self, revision_id: str, payload: dict, provenance: dict | None = None) -> ProtocolRevision:
        payload = normalize_protocol_payload(payload)
        validate_protocol_payload(payload)
        row = self.session.get(ProtocolRevision, revision_id)
        if row is None:
            raise V1NotFoundError(f"protocol revision not found: {revision_id}")
        if row.state != "draft":
            raise V1InvariantError("only draft protocol revisions can be edited")
        row.payload_json = canonical_json_bytes(payload).decode("utf-8")
        row.provenance_json = canonical_json_bytes(provenance or {}).decode("utf-8")
        row.content_hash = content_hash(payload)
        self.session.flush()
        return row

    def publish(self, revision_id: str) -> ProtocolRevision:
        row = self.session.get(ProtocolRevision, revision_id)
        if row is None:
            raise V1NotFoundError(f"protocol revision not found: {revision_id}")
        if row.state != "draft":
            raise V1InvariantError(f"only draft protocol revisions can be published: {revision_id}")
        project = self.session.get(Project, row.project_id)
        if project is None:
            raise V1NotFoundError(f"project not found: {row.project_id}")

        prior = self.session.scalars(
            select(ProtocolRevision).where(
                ProtocolRevision.project_id == row.project_id,
                ProtocolRevision.state == "published",
                ProtocolRevision.id != row.id,
            )
        ).all()
        for item in prior:
            item.state = "superseded"

        row.state = "published"
        row.published_at = utc_now()
        project.current_protocol_revision_id = row.id
        project.status = "open"
        self.session.flush()
        return row

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentProtocolIdentity:
    project_id: str
    protocol_revision_id: str


def get_current_protocol_identity(session: Session, project_id: str) -> CurrentProtocolIdentity:
    project = session.get(Project, project_id)
    if project is None:
        raise V1NotFoundError(f"project not found: {project_id}")
    if not project.current_protocol_revision_id:
        raise V1InvariantError("project has no published current protocol")
    protocol = session.get(ProtocolRevision, project.current_protocol_revision_id)
    if protocol is None or protocol.state != "published" or protocol.project_id != project.id:
        raise V1InvariantError("current protocol pointer is invalid")
    return CurrentProtocolIdentity(project_id=project.id, protocol_revision_id=protocol.id)


def ensure_project_exists(session: Session, project_id: str) -> None:
    if session.get(Project, project_id) is None:
        raise V1NotFoundError(f"project not found: {project_id}")

import json


def get_protocol_payload(session: Session, revision_id: str) -> dict:
    row = session.get(ProtocolRevision, revision_id)
    if row is None:
        raise V1NotFoundError(f"protocol revision not found: {revision_id}")
    try:
        payload = json.loads(row.payload_json)
    except json.JSONDecodeError as exc:
        raise V1InvariantError(f"protocol payload is invalid JSON: {revision_id}") from exc
    if not isinstance(payload, dict):
        raise V1InvariantError(f"protocol payload must be an object: {revision_id}")
    return payload
