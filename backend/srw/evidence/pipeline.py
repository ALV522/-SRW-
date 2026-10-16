from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.errors import V1NotFoundError
from srw.modules.candidate.commands import add_claim
from srw.modules.candidate.models import Claim, Source
from srw.evidence.grounding import enrich_source_locator
from srw.providers.contracts import ClaimProposal, ProviderOutputInvalidError
from srw.privacy.service import build_source_privacy_projection, rebind_privacy_safe_proposals


@dataclass(frozen=True, slots=True)
class EvidenceExtractionResult:
    source_id: str
    proposed: int
    created: int
    duplicate: int
    rejected: int
    claim_ids: tuple[str, ...]


def _validate_proposal(proposal: ClaimProposal) -> None:
    if not isinstance(proposal.normalized_text, str) or not proposal.normalized_text.strip():
        raise ProviderOutputInvalidError("claim normalized_text must be non-empty")
    if not isinstance(proposal.locator, dict):
        raise ProviderOutputInvalidError("claim locator must be an object")
    if proposal.confidence is not None:
        if not isinstance(proposal.confidence, (int, float)) or not 0.0 <= float(proposal.confidence) <= 1.0:
            raise ProviderOutputInvalidError("claim confidence must be between 0 and 1")
    if not isinstance(proposal.reason, str):
        raise ProviderOutputInvalidError("claim reason must be a string")
    if not isinstance(proposal.metadata, dict):
        raise ProviderOutputInvalidError("claim metadata must be an object")


def persist_source_claims(session: Session, source_id: str, proposals) -> EvidenceExtractionResult:
    source = session.get(Source, source_id)
    if source is None:
        raise V1NotFoundError(f"source not found: {source_id}")

    proposals = tuple(proposals)
    accepted_proposals = []
    rejected = 0
    for proposal in proposals:
        if not isinstance(proposal, ClaimProposal):
            raise ProviderOutputInvalidError("provider returned non-claim proposal values")
        _validate_proposal(proposal)
        locator = enrich_source_locator(source, proposal.locator)
        if locator is None:
            rejected += 1
            continue
        accepted_proposals.append(ClaimProposal(
            normalized_text=proposal.normalized_text,
            locator=locator,
            confidence=proposal.confidence,
            reason=proposal.reason,
            metadata=dict(proposal.metadata or {}),
        ))

    known_ids = set(
        session.scalars(
            select(Claim.id).where(
                Claim.candidate_id == source.candidate_id,
                Claim.source_id == source.id,
            )
        ).all()
    )
    created = 0
    duplicate = 0
    claim_ids: list[str] = []
    for proposal in accepted_proposals:
        metadata = {
            "confidence": proposal.confidence,
            "reason": proposal.reason,
            **proposal.metadata,
        }
        row = add_claim(
            session,
            source.candidate_id,
            source.id,
            proposal.normalized_text,
            locator=proposal.locator,
            authority="model_proposal",
            proposal_metadata=metadata,
        )
        claim_ids.append(row.id)
        if row.id in known_ids:
            duplicate += 1
        else:
            created += 1
            known_ids.add(row.id)

    return EvidenceExtractionResult(
        source_id=source.id,
        proposed=len(proposals),
        created=created,
        duplicate=duplicate,
        rejected=rejected,
        claim_ids=tuple(claim_ids),
    )

def extract_source_claims(session: Session, source_id: str, provider_runtime) -> EvidenceExtractionResult:
    """Compatibility synchronous path; durable workers should split provider I/O from persistence."""
    source = session.get(Source, source_id)
    if source is None:
        raise V1NotFoundError(f"source not found: {source_id}")
    projection = build_source_privacy_projection(session, source)
    proposals = provider_runtime.extract_claims(session, source_text=projection.safe_text)
    proposals = rebind_privacy_safe_proposals(projection, proposals)
    return persist_source_claims(session, source_id, proposals)

