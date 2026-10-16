from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class CandidateStageTransition(V1Base):
    __tablename__ = "candidate_stage_transition"
    __table_args__ = (
        Index("ix_v1_candidate_stage_transition_candidate_time", "candidate_id", "created_at"),
        Index("ix_v1_candidate_stage_transition_project_time", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, index=True)
    from_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    to_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="human")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class OfferRecord(V1Base):
    __tablename__ = "offer_record"
    __table_args__ = (
        Index("ix_v1_offer_candidate_time", "candidate_id", "created_at"),
        Index("ix_v1_offer_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft", index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    compensation_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_start_date: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="human")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
