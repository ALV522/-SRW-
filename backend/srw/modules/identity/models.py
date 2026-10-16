from __future__ import annotations

from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class CandidateIdentityReview(V1Base):
    __tablename__ = "candidate_identity_review"
    __table_args__ = (
        UniqueConstraint("project_id", "candidate_a_id", "candidate_b_id", name="uq_v1_identity_review_pair"),
        CheckConstraint("status IN ('pending','confirmed_same','confirmed_distinct','dismissed')", name="ck_v1_identity_review_status"),
        Index("ix_v1_identity_review_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    candidate_a_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False)
    candidate_b_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False)
    match_reason: Mapped[str] = mapped_column(String(80), nullable=False)
    match_value_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="deterministic_contact")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    resolution_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resolved_by: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
