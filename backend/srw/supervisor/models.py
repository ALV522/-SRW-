"""Carrier session records for the Supervisor attach protocol (ADR-0003 S3).

The session TOKEN never leaves Supervisor memory; what is persisted is the
session RECORD: which carrier attached, under which Supervisor instance, when
it was last seen, and whether/when it was revoked. That record is what makes
revocation auditable (detach, timeout, Supervisor exit) without ever putting a
bearer secret on disk.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class CarrierSession(V1Base):
    __tablename__ = "carrier_session"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attach_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    supervisor_instance_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    edition: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    carrier: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(120), nullable=False, default="")
