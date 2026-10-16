from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base


class Candidate(V1Base):
    __tablename__ = "candidate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    pipeline_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="new", index=True)
    current_material_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    merged_into_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidate.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CandidateContact(V1Base):
    __tablename__ = "candidate_contact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    confirmed_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    user_confirmed: Mapped[bool] = mapped_column(nullable=False, default=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)



class Source(V1Base):
    __tablename__ = "source"
    __table_args__ = (
        UniqueConstraint("candidate_id", "content_hash", "source_kind", name="uq_v1_source_candidate_hash_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    blob_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False, default="text/plain")
    text_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MaterialRevision(V1Base):
    __tablename__ = "material_revision"
    __table_args__ = (
        UniqueConstraint("candidate_id", "revision", name="uq_v1_material_candidate_revision"),
        Index("ix_v1_material_candidate_published", "candidate_id", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_set_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MaterialSourceBinding(V1Base):
    __tablename__ = "material_source_binding"
    __table_args__ = (
        UniqueConstraint("material_revision_id", "source_id", name="uq_v1_material_source"),
    )

    material_revision_id: Mapped[str] = mapped_column(ForeignKey("material_revision.id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id", ondelete="RESTRICT"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Claim(V1Base):
    __tablename__ = "claim"
    __table_args__ = (
        CheckConstraint("confirmation_state IN ('unreviewed','confirmed','rejected','superseded')", name="ck_v1_claim_confirmation"),
        Index("ix_v1_claim_candidate_state", "candidate_id", "confirmation_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source.id", ondelete="RESTRICT"), nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_locator_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    proposal_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    authority: Mapped[str] = mapped_column(String(32), nullable=False, default="source")
    confirmation_state: Mapped[str] = mapped_column(String(20), nullable=False, default="unreviewed")
    supersedes_claim_id: Mapped[str | None] = mapped_column(ForeignKey("claim.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
