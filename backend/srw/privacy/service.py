from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.modules.candidate.models import Candidate, CandidateContact, Source
from srw.providers.contracts import ClaimProposal
from srw.privacy.redaction import RedactionResult, redact_personal_data


@dataclass(frozen=True, slots=True)
class PrivacyProjection:
    source_id: str
    original_text: str
    safe_text: str
    redaction: RedactionResult


def _known_names(session: Session, candidate_id: str) -> tuple[str, ...]:
    candidate = session.get(Candidate, candidate_id)
    contact = session.scalar(select(CandidateContact).where(CandidateContact.candidate_id == candidate_id))
    values: list[str] = []
    for value in (candidate.display_name if candidate else "", contact.display_name if contact else ""):
        value = str(value or "").strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def build_source_privacy_projection(session: Session, source: Source) -> PrivacyProjection:
    result = redact_personal_data(
        source.text_content,
        known_names=_known_names(session, source.candidate_id),
        preserve_length=True,
    )
    return PrivacyProjection(source.id, source.text_content, result.text, result)


def _locator_start(safe_text: str, quote: str, locator: dict) -> int | None:
    raw_start = locator.get("char_start")
    if isinstance(raw_start, int) and raw_start >= 0 and safe_text[raw_start:raw_start + len(quote)] == quote:
        return raw_start
    start = safe_text.find(quote)
    if start < 0:
        return None
    # Without an explicit offset, repeated quotes are not safe enough to bind to evidence.
    if safe_text.find(quote, start + 1) >= 0:
        return None
    return start


def rebind_privacy_safe_proposals(projection: PrivacyProjection, proposals) -> tuple[ClaimProposal, ...]:
    """Map safe-provider quotes back to local source offsets.

    Claims whose quoted evidence intersects a redacted span are discarded: a remote
    provider is never allowed to create a judgment claim about data it was not shown.
    """
    output: list[ClaimProposal] = []
    for proposal in proposals:
        if not isinstance(proposal, ClaimProposal):
            output.append(proposal)
            continue
        locator = dict(proposal.locator or {})
        quote = str(locator.get("quote") or "").strip()
        if not quote or "█" in quote:
            continue
        start = _locator_start(projection.safe_text, quote, locator)
        if start is None:
            # Let normal grounding validation reject hallucinated / rewritten quotes.
            output.append(proposal)
            continue
        end = start + len(quote)
        if any(span.start < end and span.end > start for span in projection.redaction.spans):
            continue
        original_quote = projection.original_text[start:end]
        locator.update({
            "quote": original_quote,
            "char_start": start,
            "char_end": end,
            "privacy_projected": True,
        })
        metadata = dict(proposal.metadata or {})
        metadata["privacy_scoring_view"] = True
        output.append(ClaimProposal(
            normalized_text=proposal.normalized_text,
            locator=locator,
            confidence=proposal.confidence,
            reason=proposal.reason,
            metadata=metadata,
        ))
    return tuple(output)
