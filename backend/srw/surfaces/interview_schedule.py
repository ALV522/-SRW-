"""Core-authored first-interview scheduling targets for the operator dashboard.

A target is a navigation hint, not a durable authorization. The event-write
route rechecks the exact project, protocol and material identities when the
operator saves the schedule.
"""
from __future__ import annotations

import json

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from srw.modules.candidate.models import Candidate, MaterialRevision
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.protocol.models import Project, ProtocolRevision


def get_interview_schedule_targets(session: Session, *, limit: int = 8) -> dict:
    """Return explicit first-interview targets backed by current Core state.

    Multiple eligible candidates remain separate rows so HR chooses the
    intended person. A candidate with an existing scheduled/completed
    interview is not offered this first-interview shortcut; later rounds
    remain available from the candidate workspace.
    """
    has_interview = (
        select(RecruitmentEvent.id)
        .where(
            RecruitmentEvent.candidate_id == Candidate.id,
            RecruitmentEvent.event_type == "interview",
            RecruitmentEvent.event_state.in_(("scheduled", "completed")),
        )
        .exists()
    )
    rows = session.execute(
        select(Candidate, Project, ProtocolRevision, MaterialRevision)
        .join(Project, Candidate.project_id == Project.id)
        .join(
            ProtocolRevision,
            and_(
                ProtocolRevision.id == Project.current_protocol_revision_id,
                ProtocolRevision.project_id == Project.id,
                ProtocolRevision.state == "published",
            ),
        )
        .join(
            MaterialRevision,
            and_(
                MaterialRevision.id == Candidate.current_material_revision_id,
                MaterialRevision.candidate_id == Candidate.id,
                MaterialRevision.published_at.is_not(None),
            ),
        )
        .where(
            Project.status == "open",
            Candidate.archived.is_(False),
            Candidate.merged_into_candidate_id.is_(None),
            ~Candidate.pipeline_stage.in_(("rejected", "withdrawn", "offer", "hired")),
            ~has_interview,
        )
        .order_by(Project.title, Candidate.created_at, Candidate.id)
    ).all()

    targets = []
    for candidate, project, protocol, material in rows:
        try:
            payload = json.loads(protocol.payload_json or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        criterion_keys = {
            str(item.get("criterion_key") or "")
            for item in (payload.get("criteria") or [])
            if isinstance(item, dict) and item.get("criterion_key")
        }
        interview_keys = []
        for stage in payload.get("assessment_stages") or []:
            if not isinstance(stage, dict):
                continue
            if stage.get("stage_key") not in {"interview"} and stage.get("name") != "面试":
                continue
            interview_keys.extend(
                key for key in (stage.get("criteria") or [])
                if isinstance(key, str) and key in criterion_keys
            )
        if not interview_keys:
            continue
        targets.append({
            "kind": "ready_to_schedule_interview",
            "action_type": "schedule_interview",
            "project_id": project.id,
            "project_title": project.title,
            "candidate_id": candidate.id,
            "candidate_name": candidate.display_name,
            "event_id": "",
            "protocol_revision_id": protocol.id,
            "material_revision_id": material.id,
            "title": "待安排首轮面试",
            "detail": f"材料 R{material.revision} · 岗位标准 R{protocol.revision}",
        })
    safe_limit = max(1, min(20, int(limit)))
    return {"items": targets[:safe_limit], "total": len(targets)}
