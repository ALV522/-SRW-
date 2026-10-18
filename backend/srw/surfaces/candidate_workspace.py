from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import decision_context_hash
from srw.modules.candidate.models import Candidate, Claim, MaterialRevision, MaterialSourceBinding, Source
from srw.modules.decision.models import CriterionJudgment, HumanDecision
from srw.modules.decision.lineage import latest_stale_decision
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.work.derive import WorkSpec, derive_work_specs
from srw.modules.work.models import WorkItem
from srw.modules.work.next_action import NextAction, NextActionType, choose_next_action


@dataclass(frozen=True, slots=True)
class CriterionWorkspaceRow:
    criterion_key: str
    name: str
    status_label: str
    evidence_label: str
    reason: str
    gap: str
    probe: str
    decision_critical: bool
    verification_required: bool
    origin: str = ""
    carried_forward: bool = False


@dataclass(frozen=True, slots=True)
class SourceWorkspaceRow:
    source_id: str
    source_kind: str
    media_type: str
    filename: str
    text_preview: str
    has_text: bool
    in_current_material: bool
    content_url: str


@dataclass(frozen=True, slots=True)
class ClaimWorkspaceRow:
    claim_id: str
    source_id: str
    normalized_text: str
    locator: dict
    authority: str
    confirmation_state: str
    confidence: float | None
    proposal_reason: str


@dataclass(frozen=True, slots=True)
class CandidateWorkspace:
    candidate_id: str
    display_name: str
    decision_context_hash: str
    decision_ready: bool
    readiness_label: str
    blocking_count: int
    next_action: NextAction
    decision_label: str = ""
    decision_reason: str = ""
    stale_decision_id: str = ""
    stale_decision_label: str = ""
    stale_decision_reason: str = ""
    stale_decision_context_hash: str = ""
    decision_reaffirmable: bool = False
    criteria: tuple[CriterionWorkspaceRow, ...] = ()
    sources: tuple[SourceWorkspaceRow, ...] = ()
    claims: tuple[ClaimWorkspaceRow, ...] = ()


_STATUS_LABEL = {
    "met": "已确认",
    "partial": "证据一般",
    "missing": "仍需核实",
    "conflict": "存在矛盾",
    "not_met": "未满足",
}
_EVIDENCE_LABEL = {"strong": "强", "medium": "证据一般", "weak": "较弱", "none": "无"}
_DECISION_LABEL = {"advance": "继续推进", "reject": "不再推进", "hold": "暂缓决定"}


def _payload(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise V1InvariantError("current protocol payload is invalid") from exc
    if not isinstance(value, dict):
        raise V1InvariantError("current protocol payload must be an object")
    return value


def _json_object(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def get_candidate_workspace(
    session: Session,
    candidate_id: str,
    *,
    evaluation_policy_revision: str,
) -> CandidateWorkspace:
    identity = session.execute(
        select(Candidate, Project, ProtocolRevision, MaterialRevision)
        .join(Project, Candidate.project_id == Project.id)
        .outerjoin(ProtocolRevision, ProtocolRevision.id == Project.current_protocol_revision_id)
        .outerjoin(MaterialRevision, MaterialRevision.id == Candidate.current_material_revision_id)
        .where(Candidate.id == candidate_id)
    ).first()
    if identity is None:
        if session.get(Candidate, candidate_id) is None:
            raise V1NotFoundError(f"candidate not found: {candidate_id}")
        raise V1InvariantError("candidate project relationship is invalid")
    candidate, project, protocol, material = identity
    # Intake and material review must remain usable before a protocol is published.
    # A missing decision context must never become a synthetic valid decision.
    if (project.current_protocol_revision_id and protocol is None) or (
        protocol is not None and (protocol.state != "published" or protocol.project_id != project.id)
    ):
        raise V1InvariantError("candidate current protocol pointer is invalid")
    if (candidate.current_material_revision_id and material is None) or (
        material is not None and material.candidate_id != candidate.id
    ):
        raise V1InvariantError("candidate current material pointer is invalid")
    context_hash = (
        decision_context_hash(protocol.id, material.id, evaluation_policy_revision)
        if protocol is not None and material is not None else ""
    )

    judgments = session.scalars(
        select(CriterionJudgment).where(
            CriterionJudgment.candidate_id == candidate.id,
            CriterionJudgment.decision_context_hash == context_hash,
        )
    ).all()
    by_key = {row.criterion_key: row for row in judgments}
    work_items = session.scalars(
        select(WorkItem).where(
            WorkItem.candidate_id == candidate.id,
            WorkItem.decision_context_hash == context_hash,
            WorkItem.state.in_(("open", "in_progress")),
        )
    ).all()
    current_decision = session.scalar(
        select(HumanDecision)
        .where(HumanDecision.candidate_id == candidate.id, HumanDecision.decision_context_hash == context_hash)
        .order_by(HumanDecision.created_at.desc(), HumanDecision.id.desc())
        .limit(1)
    )

    material_rows = session.execute(
        select(Source, Claim, MaterialSourceBinding.source_id)
        .outerjoin(Claim, Claim.source_id == Source.id)
        .outerjoin(
            MaterialSourceBinding,
            and_(
                MaterialSourceBinding.source_id == Source.id,
                MaterialSourceBinding.material_revision_id == (material.id if material is not None else ""),
            ),
        )
        .where(Source.candidate_id == candidate.id)
        .order_by(Source.created_at.desc(), Source.id.desc(), Claim.created_at.asc(), Claim.id.asc())
    ).all()
    source_views: dict[str, SourceWorkspaceRow] = {}
    claim_views: list[ClaimWorkspaceRow] = []
    for source, claim, current_source_id in material_rows:
        if source.id not in source_views:
            source_metadata = _json_object(source.metadata_json)
            source_views[source.id] = SourceWorkspaceRow(
                source_id=source.id,
                source_kind=source.source_kind,
                media_type=source.media_type,
                filename=str(source_metadata.get("filename") or ""),
                text_preview=source.text_content[:240],
                has_text=bool(source.text_content.strip()),
                in_current_material=current_source_id is not None,
                content_url=f"/api/v1/sources/{source.id}/content",
            )
        if claim is not None:
            proposal_metadata = _json_object(claim.proposal_metadata_json)
            confidence = proposal_metadata.get("confidence")
            claim_views.append(
                ClaimWorkspaceRow(
                    claim_id=claim.id,
                    source_id=claim.source_id,
                    normalized_text=claim.normalized_text,
                    locator=_json_object(claim.source_locator_json),
                    authority=claim.authority,
                    confirmation_state=claim.confirmation_state,
                    confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                    proposal_reason=str(proposal_metadata.get("reason") or ""),
                )
            )

    if protocol is None or material is None:
        reason = (
            "岗位评价标准尚未正式发布；可先收件和核实材料，但不能提交招聘判断"
            if protocol is None else
            "候选人尚无已发布材料；可先导入材料，但不能提交招聘判断"
        )
        return CandidateWorkspace(
            candidate_id=candidate.id,
            display_name=candidate.display_name,
            decision_context_hash="",
            decision_ready=False,
            readiness_label=reason,
            blocking_count=0,
            next_action=NextAction(type=NextActionType.WAIT_FOR_INPUT, reason=reason),
            sources=tuple(source_views.values()),
            claims=tuple(claim_views),
        )

    protocol_payload = _payload(protocol.payload_json)
    criteria_payload = [row for row in (protocol_payload.get("criteria") or []) if isinstance(row, dict)]
    rows: list[CriterionWorkspaceRow] = []
    blocking_count = 0
    for criterion in criteria_payload:
        key = str(criterion.get("criterion_key") or "").strip()
        if not key:
            continue
        judgment = by_key.get(key)
        status = judgment.status if judgment is not None else "missing"
        evidence = judgment.evidence_level if judgment is not None else "none"
        decision_critical = bool(criterion.get("decision_critical"))
        verification_required = bool(criterion.get("verification_required"))
        if (decision_critical or verification_required) and status in {"missing", "partial", "conflict"}:
            blocking_count += 1
        probes = criterion.get("verification_probes") or []
        probe = str(probes[0]) if isinstance(probes, list) and probes else ""
        rows.append(
            CriterionWorkspaceRow(
                criterion_key=key,
                name=str(criterion.get("name") or key),
                status_label=_STATUS_LABEL.get(status, status),
                evidence_label=_EVIDENCE_LABEL.get(evidence, evidence),
                reason=judgment.reason if judgment is not None else "尚无当前判断",
                gap=judgment.gap if judgment is not None else "尚无足够证据",
                probe=probe,
                decision_critical=decision_critical,
                verification_required=verification_required,
                origin=judgment.origin if judgment is not None else "",
                carried_forward=bool(judgment is not None and judgment.carried_forward_from_judgment_id),
            )
        )

    stale_decision = latest_stale_decision(session, candidate.id, current_context_hash=context_hash) if current_decision is None else None

    decision_ready = blocking_count == 0
    action_items = list(work_items)
    if not action_items:
        from srw.modules.decision.repository import JudgmentView
        views = [
            JudgmentView(
                id=row.id,
                criterion_key=row.criterion_key,
                status=row.status,
                evidence_level=row.evidence_level,
                reason=row.reason,
                gap=row.gap,
            )
            for row in judgments
        ]
        action_items = list(
            derive_work_specs(
                project_id=project.id,
                candidate_id=candidate.id,
                context_hash=context_hash,
                protocol_payload=protocol_payload,
                judgments=views,
            )
        )
    if current_decision is not None:
        next_action = NextAction(type=NextActionType.WAIT_FOR_INPUT, reason="当前决定已完成；等待新材料或下一阶段动作")
    else:
        next_action = choose_next_action(judgments, action_items, decision_ready)
    readiness_label = (
        f"已决定：{_DECISION_LABEL.get(current_decision.decision, current_decision.decision)}"
        if current_decision is not None
        else ("可以决定" if decision_ready else ("存在矛盾" if any(r.status == "conflict" for r in judgments) else f"仍需核实 {blocking_count} 项"))
    )
    return CandidateWorkspace(
        candidate_id=candidate.id,
        display_name=candidate.display_name,
        decision_context_hash=context_hash,
        decision_ready=decision_ready,
        readiness_label=readiness_label,
        blocking_count=blocking_count,
        next_action=next_action,
        decision_label=_DECISION_LABEL.get(current_decision.decision, current_decision.decision) if current_decision else "",
        decision_reason=current_decision.reason if current_decision else "",
        stale_decision_id=stale_decision.id if stale_decision else "",
        stale_decision_label=_DECISION_LABEL.get(stale_decision.decision, stale_decision.decision) if stale_decision else "",
        stale_decision_reason=stale_decision.reason if stale_decision else "",
        stale_decision_context_hash=stale_decision.decision_context_hash if stale_decision else "",
        decision_reaffirmable=bool(stale_decision is not None and current_decision is None),
        criteria=tuple(rows),
        sources=tuple(source_views.values()),
        claims=tuple(claim_views),
    )
