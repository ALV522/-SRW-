from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class AiRun(V1Base):
    """Privacy-safe execution ledger for remote/local AI operations.

    The ledger deliberately stores hashes and execution metadata only. Raw resume
    text, prompts, outputs, API keys, and provider response bodies are forbidden.
    """

    __tablename__ = "ai_run"
    __table_args__ = (
        Index("ix_v1_ai_run_project_time", "project_id", "started_at"),
        Index("ix_v1_ai_run_candidate_time", "candidate_id", "started_at"),
        Index("ix_v1_ai_run_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)
    provider_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False, default="evidence.claims.v1")
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False, default="claim-proposals.v1")
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_safety_meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running", index=True)
    error_class: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
