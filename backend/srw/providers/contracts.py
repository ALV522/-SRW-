from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


class ProviderError(RuntimeError):
    """Base class for provider-layer failures safe to classify at the API boundary."""


class ProviderNotReadyError(ProviderError):
    """Provider configuration or optional runtime dependency is unavailable."""


class ProviderFailureError(ProviderError):
    """Remote provider transport/protocol execution failed."""


class ProviderOutputInvalidError(ProviderError):
    """Provider returned data that cannot be accepted as claim proposals."""


@dataclass(frozen=True, slots=True)
class ClaimProposal:
    normalized_text: str
    locator: dict
    confidence: float | None = None
    reason: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceExtractionRequest:
    source_text: str
    model: str
    base_url: str
    api_key: str
    reasoning_effort: str


class EvidenceProvider(Protocol):
    def extract_claims(self, request: EvidenceExtractionRequest) -> Sequence[ClaimProposal]: ...
