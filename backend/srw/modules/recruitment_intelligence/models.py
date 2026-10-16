from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base

class SourcingChannelObservation(V1Base):
    __tablename__ = 'sourcing_channel_observation'
    __table_args__ = (
        Index('ix_v1_sourcing_observation_project_channel', 'project_id', 'channel'),
        Index('ix_v1_sourcing_observation_project_period', 'project_id', 'period'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('project.id', ondelete='CASCADE'), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(120), nullable=False)
    period: Mapped[str] = mapped_column(String(32), nullable=False, default='')
    sourced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contacted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    screened: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interviewed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hired: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spend_cny: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    human_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provenance: Mapped[str] = mapped_column(String(80), nullable=False, default='manual')
    notes: Mapped[str] = mapped_column(Text, nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
