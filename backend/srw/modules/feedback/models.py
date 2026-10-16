from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base

class FeedbackRecord(V1Base):
    __tablename__ = 'feedback_record'
    __table_args__ = (
        Index('ix_v1_feedback_project_status', 'project_id', 'status'),
        Index('ix_v1_feedback_candidate_time', 'candidate_id', 'created_at'),
        Index('ix_v1_feedback_content_hash', 'content_hash'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('project.id', ondelete='CASCADE'), nullable=False, index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey('candidate.id', ondelete='CASCADE'), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default='manual')
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='draft', index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    classification_json: Mapped[str] = mapped_column(Text, nullable=False, default='{}')
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default='human')
    reviewed_by: Mapped[str] = mapped_column(String(120), nullable=False, default='')
    review_reason: Mapped[str] = mapped_column(Text, nullable=False, default='')
    applied_source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    applied_material_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
