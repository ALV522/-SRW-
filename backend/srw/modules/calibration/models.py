from __future__ import annotations

from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class CriterionAnchorCase(V1Base):
    __tablename__ = "criterion_anchor_case"
    __table_args__ = (
        CheckConstraint("lifecycle IN ('observed','human_reviewed','candidate','gold')", name="ck_v1_anchor_lifecycle"),
        Index("ix_v1_anchor_project_lifecycle", "project_id", "lifecycle"),
        Index("ix_v1_anchor_project_criterion", "project_id", "criterion_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(128), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False, default="observed")
    case_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_judgment: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_evidence_level: Mapped[str] = mapped_column(String(20), nullable=False)
    first_reviewer: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    second_reviewer: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    source_case_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class JudgmentReviewItem(V1Base):
    __tablename__ = "judgment_review_item"
    __table_args__ = (
        CheckConstraint("state IN ('open','resolved')", name="ck_v1_judgment_review_state"),
        Index("ix_v1_judgment_review_project_state", "project_id", "state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidate.id", ondelete="SET NULL"), nullable=True)
    trigger: Mapped[str] = mapped_column(String(60), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    after: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    error_class: Mapped[str] = mapped_column(String(30), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    resolution_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
