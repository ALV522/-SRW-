from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from srw.modules.candidate.models import Candidate
from srw.modules.protocol.models import Project
from srw.modules.work.models import WorkItem


@dataclass(frozen=True, slots=True)
class WorkbenchItem:
    work_item_id: str
    project_id: str
    project_title: str
    candidate_id: str
    candidate_name: str
    criterion_name: str
    action_type: str
    reason: str


@dataclass(frozen=True, slots=True)
class Workbench:
    items: tuple[WorkbenchItem, ...]
    conflict_count: int
    verify_count: int
    ready_count: int


# Priority is explicit: alphabetical task-type order is not business priority.
_RANK = {
    "RESOLVE_CONFLICT": 0,
    "VERIFY_CRITERION": 1,
    "RUN_SCREEN": 2,
    "PREPARE_INTERVIEW": 3,
    "REVIEW_REEVALUATION": 4,
    "MAKE_DECISION": 5,
}


def get_workbench(
    session: Session, *, evaluation_policy_revision: str, project_id: str | None = None
) -> Workbench:
    rank = case(*[(WorkItem.type == kind, priority) for kind, priority in _RANK.items()], else_=99)
    conditions = [
        WorkItem.state.in_(("open", "in_progress")),
        Candidate.archived.is_(False),
        Project.status != "archived",
        WorkItem.protocol_revision_id == Project.current_protocol_revision_id,
        WorkItem.material_revision_id == Candidate.current_material_revision_id,
    ]
    if project_id is not None:
        conditions.append(WorkItem.project_id == project_id)

    ranked = (
        select(
            WorkItem.id.label("wid"),
            WorkItem.project_id,
            WorkItem.candidate_id,
            WorkItem.criterion_name,
            WorkItem.type,
            WorkItem.reason,
            rank.label("business_rank"),
            WorkItem.priority.label("item_priority"),
            WorkItem.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=WorkItem.candidate_id,
                order_by=(rank, WorkItem.priority, WorkItem.created_at, WorkItem.id),
            )
            .label("rn"),
        )
        .join(Candidate, Candidate.id == WorkItem.candidate_id)
        .join(Project, Project.id == WorkItem.project_id)
        .where(*conditions)
        .subquery()
    )
    rows = session.execute(
        select(
            ranked.c.wid,
            ranked.c.project_id,
            Project.title,
            ranked.c.candidate_id,
            Candidate.display_name,
            ranked.c.criterion_name,
            ranked.c.type,
            ranked.c.reason,
        )
        .join(Project, Project.id == ranked.c.project_id)
        .join(Candidate, Candidate.id == ranked.c.candidate_id)
        .where(ranked.c.rn == 1)
        .order_by(
            ranked.c.business_rank,
            ranked.c.item_priority,
            ranked.c.created_at,
            ranked.c.wid,
        )
    ).all()
    items = tuple(WorkbenchItem(*row) for row in rows)
    return Workbench(
        items,
        sum(i.action_type == "RESOLVE_CONFLICT" for i in items),
        sum(i.action_type == "VERIFY_CRITERION" for i in items),
        sum(i.action_type == "MAKE_DECISION" for i in items),
    )
