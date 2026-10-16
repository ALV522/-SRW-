from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class WorkItem(V1Base):
    __tablename__ = "work_item"
    __table_args__ = (
        CheckConstraint("state IN ('open','in_progress','resolved','superseded')", name="ck_v1_work_item_state"),
        Index("ix_v1_work_open_priority", "state", "priority", "project_id"),
        Index("ix_v1_work_candidate_context", "candidate_id", "decision_context_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=True)
    criterion_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    criterion_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    protocol_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    material_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision_context_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
