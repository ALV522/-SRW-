from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from srw.providers.contracts import (
    ClaimProposal,
    EvidenceExtractionRequest,
    ProviderFailureError,
    ProviderNotReadyError,
    ProviderOutputInvalidError,
)
from srw.runtime.capabilities import CapabilityRegistry
from srw.runtime.settings import RuntimeSettingsRepository, SecretStore


@dataclass(frozen=True, slots=True)
class PreparedEvidenceCall:
    provider: object
    request: EvidenceExtractionRequest


class ProviderRuntime:
    """Resolve and execute a configured provider only at the moment it is needed."""

    def __init__(self, *, registry: CapabilityRegistry, secrets: SecretStore) -> None:
        self.registry = registry
        self.secrets = secrets

    def prepare_evidence_call(self, session: Session, *, source_text: str) -> PreparedEvidenceCall:
        """Resolve settings/provider while a short DB session is open. No remote I/O occurs here."""
        preferences = RuntimeSettingsRepository(session).get_provider_profile("text_ai")
        if not preferences.model.strip():
            raise ProviderNotReadyError("provider model is not configured")
        if not preferences.base_url.strip():
            raise ProviderNotReadyError("provider base URL is not configured")
        api_key = self.secrets.get("provider_api_key")
        if not api_key:
            raise ProviderNotReadyError("provider API key is not configured")

        capability_name = f"provider.{preferences.provider_type}"
        if not self.registry.available(capability_name):
            raise ProviderNotReadyError(f"provider runtime is unavailable: {preferences.provider_type}")
        try:
            provider = self.registry.resolve(capability_name)
        except (ImportError, ModuleNotFoundError) as exc:
            raise ProviderNotReadyError(f"provider dependency is unavailable: {preferences.provider_type}") from exc
        except ProviderNotReadyError:
            raise
        except Exception as exc:
            raise ProviderFailureError("provider runtime failed to load") from exc

        request = EvidenceExtractionRequest(
            source_text=source_text,
            model=preferences.model,
            base_url=preferences.base_url,
            api_key=api_key,
            reasoning_effort=preferences.reasoning_effort,
        )
        return PreparedEvidenceCall(provider=provider, request=request)

    def execute_evidence_call(self, prepared: PreparedEvidenceCall) -> tuple[ClaimProposal, ...]:
        """Execute provider I/O without requiring or retaining a database Session."""
        try:
            values = tuple(prepared.provider.extract_claims(prepared.request))
        except (ProviderNotReadyError, ProviderFailureError, ProviderOutputInvalidError):
            raise
        except Exception as exc:
            raise ProviderFailureError("provider extraction failed") from exc
        if not all(isinstance(value, ClaimProposal) for value in values):
            raise ProviderOutputInvalidError("provider returned non-claim proposal values")
        return values

    def extract_claims(self, session: Session, *, source_text: str) -> tuple[ClaimProposal, ...]:
        """Compatibility wrapper. New durable workers should use prepare/execute separately."""
        return self.execute_evidence_call(self.prepare_evidence_call(session, source_text=source_text))
