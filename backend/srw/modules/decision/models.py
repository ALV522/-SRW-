from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class CriterionJudgment(V1Base):
    __tablename__ = "criterion_judgment"
    __table_args__ = (
        UniqueConstraint("candidate_id", "criterion_key", "decision_context_hash", name="uq_v1_judgment_context_criterion"),
        Index("ix_v1_judgment_candidate_context", "candidate_id", "decision_context_hash"),
        CheckConstraint("status IN ('met','partial','missing','conflict','not_met')", name="ck_v1_judgment_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    gap: Mapped[str] = mapped_column(Text, nullable=False, default="")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="assessment")
    carried_forward_from_judgment_id: Mapped[str | None] = mapped_column(ForeignKey("criterion_judgment.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CriterionJudgmentEvidence(V1Base):
    __tablename__ = "criterion_judgment_evidence"
    __table_args__ = (
        UniqueConstraint("judgment_id", "claim_id", name="uq_v1_judgment_claim"),
    )

    judgment_id: Mapped[str] = mapped_column(ForeignKey("criterion_judgment.id", ondelete="CASCADE"), primary_key=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claim.id", ondelete="RESTRICT"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="support")


class HumanDecision(V1Base):
    __tablename__ = "human_decision"
    __table_args__ = (
        Index("ix_v1_decision_candidate_context", "candidate_id", "decision_context_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False)
    decision_context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    override: Mapped[bool] = mapped_column(nullable=False, default=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="human")
    reaffirmed_from_decision_id: Mapped[str | None] = mapped_column(ForeignKey("human_decision.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ShortlistPublication(V1Base):
    __tablename__ = "shortlist_publication"
    __table_args__ = (
        Index("ix_v1_shortlist_project_time", "project_id", "created_at"),
        Index("ix_v1_shortlist_project_protocol", "project_id", "protocol_revision_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    protocol_revision_id: Mapped[str] = mapped_column(ForeignKey("protocol_revision.id", ondelete="RESTRICT"), nullable=False)
    evaluation_policy_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="human")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
