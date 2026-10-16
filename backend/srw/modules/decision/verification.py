from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from srw.kernel.hashing import content_hash
from srw.modules.candidate.commands import add_claim, add_source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids, get_material_source_ids, get_claim_groundings
from srw.modules.decision.commands import record_assessment
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.models import CriterionJudgment
from srw.modules.decision.repository import get_judgment_claim_ids
from srw.modules.work.derive import refresh_candidate_work_items


def carry_forward_grounded_judgments(session: Session, candidate_id: str, *, old_context_hash: str, new_context_hash: str, new_material_revision_id: str, actor: str) -> None:
    source_ids=get_material_source_ids(session,new_material_revision_id)
    old_rows=session.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==candidate_id, CriterionJudgment.decision_context_hash==old_context_hash)).all()
    for row in old_rows:
        claim_ids=get_judgment_claim_ids(session,row.id)
        if not claim_ids: continue
        groundings=get_claim_groundings(session,claim_ids)
        if groundings and all(g.source_id in source_ids for g in groundings):
            clone=CriterionJudgment(project_id=row.project_id,candidate_id=row.candidate_id,criterion_key=row.criterion_key,decision_context_hash=new_context_hash,status=row.status,evidence_level=row.evidence_level,reason=row.reason,gap=row.gap,origin='carried_forward',carried_forward_from_judgment_id=row.id)
            session.add(clone); session.flush()
            from srw.modules.decision.models import CriterionJudgmentEvidence
            for claim_id in claim_ids: session.add(CriterionJudgmentEvidence(judgment_id=clone.id,claim_id=claim_id,role='support'))
    session.flush()


def record_verification_note(session: Session, candidate_id: str, criterion_key: str, *, note: str, status: str, evidence_level: str, reason: str, gap: str, actor: str, evaluation_policy_revision: str):
    old=get_current_decision_context(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    prior_sources=get_current_source_ids(session,candidate_id)
    src=add_source(session,candidate_id,source_kind='verification_note',content_hash=content_hash({'note':note,'actor':actor,'criterion_key':criterion_key}),text_content=note,metadata={'actor':actor,'criterion_key':criterion_key})
    claim=add_claim(session,candidate_id,src.id,note,locator={'kind':'verification_note'},authority='human')
    material=MaterialRepository(session).publish_revision(candidate_id,prior_sources+[src.id],provenance={'kind':'verification','actor':actor})
    new=get_current_decision_context(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    carry_forward_grounded_judgments(session,candidate_id,old_context_hash=old.hash,new_context_hash=new.hash,new_material_revision_id=material.id,actor=actor)
    row=record_assessment(session,candidate_id,criterion_key,status=status,evidence_level=evidence_level,reason=reason,gap=gap,claim_ids=[claim.id],actor=actor,evaluation_policy_revision=evaluation_policy_revision,origin='verification')
    refresh_candidate_work_items(session,candidate_id,evaluation_policy_revision=evaluation_policy_revision)
    return row
