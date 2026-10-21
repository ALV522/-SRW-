from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import canonical_json_bytes, content_hash
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate, Claim, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.modules.protocol.repository import ensure_project_exists


def create_candidate(session: Session, project_id: str, display_name: str) -> Candidate:
    ensure_project_exists(session, project_id)
    row = Candidate(project_id=project_id, display_name=display_name.strip())
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        event_type="CANDIDATE_CREATED",
        entity_type="candidate",
        entity_id=row.id,
        actor="system",
        project_id=project_id, candidate_id=row.id,
    )
    return row


def add_source(
    session: Session,
    candidate_id: str,
    *,
    source_kind: str,
    content_hash: str,
    text_content: str,
    media_type: str = "text/plain",
    blob_hash: str | None = None,
    metadata: dict | None = None,
) -> Source:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    existing = session.scalar(
        select(Source).where(
            Source.candidate_id == candidate_id,
            Source.source_kind == source_kind,
            Source.content_hash == content_hash,
        )
    )
    if existing is not None:
        return existing
    row = Source(
        candidate_id=candidate_id,
        source_kind=source_kind,
        content_hash=content_hash,
        blob_hash=blob_hash,
        media_type=media_type,
        text_content=text_content,
        metadata_json=canonical_json_bytes(metadata or {}).decode("utf-8"),
    )
    session.add(row)
    session.flush()
    append_audit_event(
        session,
        event_type="SOURCE_ADDED",
        entity_type="source",
        entity_id=row.id,
        actor="system",
        after_hash=content_hash,
        payload={"candidate_id": candidate_id, "source_kind": source_kind},
        project_id=candidate.project_id, candidate_id=candidate_id,
    )
    return row


def publish_source_into_current_material(
    session: Session,
    candidate_id: str,
    new_source_id: str,
    *,
    supersedes_source_id: str | None = None,
):
    """Publish one Source into the candidate's current material set.

    A correction replaces only the superseded Source in the new current set;
    historical Source and MaterialRevision rows remain immutable. This is the
    shared Core operation previously nested in the full-workbench API adapter.
    """
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    source_ids: list[str] = []
    if candidate.current_material_revision_id:
        source_ids = get_current_source_ids(session, candidate_id)
    if supersedes_source_id:
        source_ids = [source_id for source_id in source_ids if source_id != supersedes_source_id]
    if new_source_id not in source_ids:
        source_ids.append(new_source_id)
    provenance = {"action": "v1_intake", "source_id": new_source_id}
    if supersedes_source_id:
        provenance["supersedes_source_id"] = supersedes_source_id
    return MaterialRepository(session).publish_revision(candidate_id, source_ids, provenance)


def add_claim(
    session: Session,
    candidate_id: str,
    source_id: str,
    normalized_text: str,
    *,
    locator: dict,
    authority: str = "source",
    proposal_metadata: dict | None = None,
) -> Claim:
    candidate = session.get(Candidate, candidate_id)
    source = session.get(Source, source_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    if source is None:
        raise V1NotFoundError(f"source not found: {source_id}")
    if source.candidate_id != candidate_id:
        raise V1InvariantError("source belongs to another candidate")
    payload = {
        "candidate_id": candidate_id,
        "source_id": source_id,
        "normalized_text": normalized_text.strip(),
        "locator": locator,
        "authority": authority,
    }
    claim_hash = content_hash(payload)
    existing = session.scalar(
        select(Claim).where(
            Claim.candidate_id == candidate_id,
            Claim.source_id == source_id,
            Claim.claim_hash == claim_hash,
        )
    )
    if existing is not None:
        return existing
    row = Claim(
        candidate_id=candidate_id,
        source_id=source_id,
        normalized_text=normalized_text.strip(),
        claim_hash=claim_hash,
        source_locator_json=canonical_json_bytes(locator).decode("utf-8"),
        proposal_metadata_json=canonical_json_bytes(proposal_metadata or {}).decode("utf-8"),
        authority=authority,
        confirmation_state="unreviewed",
    )
    session.add(row)
    session.flush()
    return row


def confirm_claim(session: Session, claim_id: str, *, accepted: bool, actor: str) -> Claim:
    row = session.get(Claim, claim_id)
    if row is None:
        raise V1NotFoundError(f"claim not found: {claim_id}")
    if row.confirmation_state == "superseded":
        raise V1InvariantError("superseded claim cannot be reviewed")
    candidate = session.get(Candidate, row.candidate_id)
    before = row.confirmation_state
    row.confirmation_state = "confirmed" if accepted else "rejected"
    session.flush()
    append_audit_event(
        session,
        event_type="CLAIM_REVIEWED",
        entity_type="claim",
        entity_id=row.id,
        actor=actor,
        reason=f"{before} -> {row.confirmation_state}",
        after_hash=row.claim_hash,
        payload={"accepted": accepted},
        project_id=candidate.project_id if candidate else None, candidate_id=row.candidate_id,
    )
    return row
