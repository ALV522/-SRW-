from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class CandidateActionPlan(V1Base):
    __tablename__ = "candidate_action_plan"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_v1_candidate_action_plan_candidate"),
        Index("ix_v1_action_plan_project_priority", "project_id", "priority"),
        Index("ix_v1_action_plan_next_contact", "next_contact_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    priority: Mapped[str] = mapped_column(String(24), nullable=False, default="normal")
    owner: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    contact_status: Mapped[str] = mapped_column(String(32), nullable=False, default="to_contact", index=True)
    next_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_result: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class InterviewScorecardSubmission(V1Base):
    __tablename__ = "interview_scorecard_submission"
    __table_args__ = (
        UniqueConstraint("event_id", "evaluator", name="uq_v1_scorecard_event_evaluator"),
        Index("ix_v1_scorecard_candidate_time", "candidate_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("recruitment_event.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluator: Mapped[str] = mapped_column(String(160), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    feedback_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    recommendation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
