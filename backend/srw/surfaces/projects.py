from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from srw.kernel.errors import V1InvariantError
from srw.modules.candidate.models import Candidate
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.work.models import WorkItem


@dataclass(frozen=True, slots=True)
class CreatedProject:
    project_id: str
    draft_revision_id: str


@dataclass(frozen=True, slots=True)
class ProjectCard:
    project_id: str
    title: str
    status: str
    protocol_state: str
    protocol_title: str
    candidate_count: int
    open_work_count: int


@dataclass(frozen=True, slots=True)
class ProjectsSurface:
    projects: tuple[ProjectCard, ...]


def create_project_with_draft(
    session: Session,
    *,
    title: str,
    role_title: str,
    brief_summary: str,
) -> CreatedProject:
    project_title = title.strip()
    role = role_title.strip()
    if not project_title:
        raise V1InvariantError("project title is required")
    if not role:
        raise V1InvariantError("role title is required")
    project = Project(title=project_title, status="draft")
    session.add(project)
    session.flush()
    draft = ProtocolRepository(session).create_draft(
        project.id,
        {
            "brief": {"title": role, "summary": brief_summary.strip()},
            "criteria": [],
            "assessment_stages": [],
            "decision_policy": {},
        },
        {"origin": "project-create"},
    )
    return CreatedProject(project_id=project.id, draft_revision_id=draft.id)


def get_projects_surface(session: Session) -> ProjectsSurface:
    candidate_counts = (
        select(
            Candidate.project_id.label("project_id"),
            func.count(Candidate.id).label("candidate_count"),
        )
        .where(Candidate.archived.is_(False))
        .group_by(Candidate.project_id)
        .subquery()
    )
    work_counts = (
        select(
            WorkItem.project_id.label("project_id"),
            func.count(WorkItem.id).label("open_work_count"),
        )
        .where(WorkItem.state.in_(("open", "in_progress")))
        .group_by(WorkItem.project_id)
        .subquery()
    )
    latest_drafts = (
        select(
            ProtocolRevision.project_id.label("project_id"),
            func.max(ProtocolRevision.revision).label("revision"),
        )
        .where(ProtocolRevision.state == "draft")
        .group_by(ProtocolRevision.project_id)
        .subquery()
    )

    current = aliased(ProtocolRevision)
    draft = aliased(ProtocolRevision)
    draft_title = func.json_extract(draft.payload_json, "$.brief.title")
    current_title = func.json_extract(current.payload_json, "$.brief.title")
    protocol_state = case(
        (and_(draft.id.is_not(None), current.id.is_not(None)), "draft_changes"),
        (draft.id.is_not(None), "draft"),
        (current.id.is_not(None), "published"),
        else_="draft",
    )

    rows = session.execute(
        select(
            Project.id,
            Project.title,
            Project.status,
            protocol_state,
            func.coalesce(draft_title, current_title, ""),
            func.coalesce(candidate_counts.c.candidate_count, 0),
            func.coalesce(work_counts.c.open_work_count, 0),
        )
        .outerjoin(candidate_counts, candidate_counts.c.project_id == Project.id)
        .outerjoin(work_counts, work_counts.c.project_id == Project.id)
        .outerjoin(current, current.id == Project.current_protocol_revision_id)
        .outerjoin(latest_drafts, latest_drafts.c.project_id == Project.id)
        .outerjoin(
            draft,
            and_(
                draft.project_id == Project.id,
                draft.revision == latest_drafts.c.revision,
                draft.state == "draft",
            ),
        )
        .order_by(Project.updated_at.desc(), Project.created_at.desc(), Project.id)
    ).all()
    return ProjectsSurface(projects=tuple(ProjectCard(*row) for row in rows))
