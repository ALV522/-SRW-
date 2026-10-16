from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.modules.decision.models import CriterionJudgment


@dataclass(frozen=True, slots=True)
class JudgmentView:
    id: str
    criterion_key: str
    status: str
    evidence_level: str
    reason: str
    gap: str


def get_judgments_for_context(session: Session, candidate_id: str, context_hash: str) -> list[JudgmentView]:
    rows = session.scalars(
        select(CriterionJudgment).where(
            CriterionJudgment.candidate_id == candidate_id,
            CriterionJudgment.decision_context_hash == context_hash,
        )
    ).all()
    return [
        JudgmentView(
            id=row.id,
            criterion_key=row.criterion_key,
            status=row.status,
            evidence_level=row.evidence_level,
            reason=row.reason,
            gap=row.gap,
        )
        for row in rows
    ]

from srw.modules.decision.models import CriterionJudgmentEvidence


def get_judgment_claim_ids(session: Session, judgment_id: str) -> list[str]:
    return list(session.scalars(select(CriterionJudgmentEvidence.claim_id).where(CriterionJudgmentEvidence.judgment_id == judgment_id)).all())
