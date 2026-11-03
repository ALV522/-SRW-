"""Manual, grounded Claim proposals without an AI Provider (#198).

This Application operation is deliberately not a human confirmation. It reuses
the authoritative Source, MaterialRevision, Claim and Audit repositories; the
existing review route remains the only way to confirm the proposed fact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.evidence.grounding import enrich_source_locator
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.commands import add_claim
from srw.modules.candidate.models import Candidate, Claim, Source
from srw.modules.candidate.repository import get_current_source_ids


@dataclass(frozen=True, slots=True)
class ManualClaimResult:
    claim: Claim
    duplicate: bool


def create_manual_claim_proposal(
    session: Session, candidate_id: str, source_id: str,
    normalized_text: str, locator: dict,
) -> ManualClaimResult:
    """Create an unreviewed, source-grounded operator proposal atomically.

    A supplied quote must be found in the current Source text. An explicit
    offset must match exactly; page hints must be backed by extractor blocks.
    An unverified locator never becomes a claim or an audit event.
    """
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    if candidate.archived or candidate.merged_into_candidate_id:
        raise V1InvariantError("archived or merged candidate cannot receive new claims")
    source = session.get(Source, source_id)
    if source is None:
        raise V1NotFoundError(f"source not found: {source_id}")
    if source.candidate_id != candidate_id:
        raise V1InvariantError("source belongs to another candidate")
    if source_id not in get_current_source_ids(session, candidate_id):
        raise V1InvariantError("source is not in the current published material revision")

    if not isinstance(normalized_text, str) or not 0 < len(normalized_text.strip()) <= 2000:
        raise V1InvariantError("normalized_text must be 1-2000 characters")
    normalized_text = normalized_text.strip()
    if not isinstance(locator, dict) or set(locator) - {"quote", "char_start", "page"}:
        raise V1InvariantError("locator supports only quote, char_start and page")
    quote = locator.get("quote")
    if not isinstance(quote, str) or not 0 < len(quote.strip()) <= 1000:
        raise V1InvariantError("locator quote must be 1-1000 characters")
    quote = quote.strip()
    if "char_start" in locator:
        offset = locator["char_start"]
        if type(offset) is not int or offset < 0 or source.text_content[offset:offset + len(quote)] != quote:
            raise V1InvariantError("locator char_start does not match source text")
    if "page" in locator and (type(locator["page"]) is not int or locator["page"] < 1):
        raise V1InvariantError("locator page must be a positive integer")

    supplied = {"quote": quote}
    if "char_start" in locator:
        supplied["char_start"] = locator["char_start"]
    if "page" in locator:
        supplied["page"] = locator["page"]
    grounded = enrich_source_locator(source, supplied)
    if grounded is None:
        raise V1InvariantError("locator quote is absent or ambiguous in source text")
    if "page" in supplied:
        try:
            meta = json.loads(source.metadata_json or "{}")
        except (ValueError, TypeError):
            meta = {}
        extractor = meta.get("extractor", {}) if isinstance(meta, dict) else {}
        blocks = extractor.get("grounding_blocks", []) if isinstance(extractor, dict) else []
        if not isinstance(blocks, list):
            blocks = []
        start = grounded["char_start"]
        if not any(
            isinstance(block, dict) and block.get("page") == supplied["page"]
            and type(block.get("char_start")) is int and type(block.get("char_end")) is int
            and block["char_start"] <= start < block["char_end"]
            for block in blocks
        ):
            raise V1InvariantError("locator page cannot be verified against source extraction")

    authority = "human_proposal"
    claim_hash = content_hash({
        "candidate_id": candidate_id, "source_id": source_id,
        "normalized_text": normalized_text, "locator": grounded, "authority": authority,
    })
    existing = session.scalar(select(Claim).where(
        Claim.candidate_id == candidate_id, Claim.source_id == source_id,
        Claim.claim_hash == claim_hash,
    ))
    if existing is not None:
        return ManualClaimResult(existing, True)

    row = add_claim(
        session, candidate_id, source_id, normalized_text,
        locator=grounded, authority=authority,
        proposal_metadata={"origin": "manual_source_grounded"},
    )
    append_audit_event(
        session, event_type="CLAIM_PROPOSED_MANUALLY",
        entity_type="claim", entity_id=row.id, actor="human",
        after_hash=row.claim_hash, project_id=candidate.project_id,
        candidate_id=candidate_id,
        payload={
            "source_id": source_id, "source_content_hash": source.content_hash,
            "material_revision_id": candidate.current_material_revision_id,
            "claim_hash": row.claim_hash,
        },
    )
    return ManualClaimResult(row, False)
