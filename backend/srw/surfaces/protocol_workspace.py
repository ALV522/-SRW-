from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.protocol.models import Project, ProtocolRevision


@dataclass(frozen=True, slots=True)
class ProtocolWorkspaceView:
    revision_id: str
    revision: int
    token: str
    title: str
    brief: dict
    criteria: tuple[dict, ...]
    assessment_stages: tuple[dict, ...]
    decision_policy: dict
    recruitment_context: dict


@dataclass(frozen=True, slots=True)
class ProtocolWorkspace:
    project_id: str
    project_title: str
    current_revision_id: str | None
    draft_revision_id: str | None
    current: ProtocolWorkspaceView | None
    draft: ProtocolWorkspaceView | None


def _view(row: ProtocolRevision | None) -> ProtocolWorkspaceView | None:
    if row is None:
        return None
    try:
        payload = json.loads(row.payload_json)
    except json.JSONDecodeError as exc:
        raise V1InvariantError("protocol payload is invalid") from exc
    if not isinstance(payload, dict):
        raise V1InvariantError("protocol payload must be an object")
    brief = payload.get("brief") or {}
    if not isinstance(brief, dict):
        raise V1InvariantError("protocol brief must be an object")
    return ProtocolWorkspaceView(
        row.id,
        row.revision,
        f"{row.id}:{row.content_hash}",
        str(brief.get("title") or ""),
        brief,
        tuple(payload.get("criteria") or []),
        tuple(payload.get("assessment_stages") or []),
        payload.get("decision_policy") or {},
        payload.get("recruitment_context") or {},
    )


def get_protocol_workspace(session: Session, project_id: str) -> ProtocolWorkspace:
    current = aliased(ProtocolRevision)
    draft = aliased(ProtocolRevision)
    latest_draft = (
        select(
            ProtocolRevision.project_id.label("project_id"),
            func.max(ProtocolRevision.revision).label("revision"),
        )
        .where(
            ProtocolRevision.project_id == project_id,
            ProtocolRevision.state == "draft",
        )
        .group_by(ProtocolRevision.project_id)
        .subquery()
    )

    row = session.execute(
        select(Project, current, draft)
        .outerjoin(current, current.id == Project.current_protocol_revision_id)
        .outerjoin(latest_draft, latest_draft.c.project_id == Project.id)
        .outerjoin(
            draft,
            and_(
                draft.project_id == Project.id,
                draft.revision == latest_draft.c.revision,
                draft.state == "draft",
            ),
        )
        .where(Project.id == project_id)
    ).first()
    if row is None:
        raise V1NotFoundError(f"project not found: {project_id}")

    project, current_row, draft_row = row
    if current_row is not None and current_row.state != "published":
        current_row = None
    return ProtocolWorkspace(
        project.id,
        project.title,
        current_row.id if current_row else None,
        draft_row.id if draft_row else None,
        _view(current_row),
        _view(draft_row),
    )
