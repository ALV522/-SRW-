from __future__ import annotations

import json
from typing import Any

from srw.providers.contracts import (
    ClaimProposal,
    EvidenceExtractionRequest,
    ProviderFailureError,
    ProviderNotReadyError,
    ProviderOutputInvalidError,
)


def _json_content(text: str) -> Any:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProviderOutputInvalidError("provider response is not valid JSON") from exc


class OpenAICompatibleProvider:
    """Small optional adapter; httpx is imported only when a request is executed."""

    def extract_claims(self, request: EvidenceExtractionRequest) -> tuple[ClaimProposal, ...]:
        try:
            import httpx  # type: ignore
        except ImportError as exc:
            raise ProviderNotReadyError("optional provider pack is not installed") from exc

        base_url = request.base_url.rstrip("/")
        payload = {
            "model": request.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract only candidate facts directly supported by the supplied material. "
                        "Return JSON object {\"claims\":[{\"normalized_text\":str,\"locator\":{\"quote\":str},"
                        "\"confidence\":number|null,\"reason\":str}]}. locator.quote must be a verbatim substring of the supplied material. Do not score, evaluate, or decide."
                    ),
                },
                {"role": "user", "content": request.source_text},
            ],
            "response_format": {"type": "json_object"},
        }
        if request.reasoning_effort:
            payload["reasoning_effort"] = request.reasoning_effort
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {request.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            raise ProviderFailureError("provider HTTP request failed") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderOutputInvalidError("provider response is missing message content") from exc
        data = _json_content(str(content))
        if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
            raise ProviderOutputInvalidError("provider response must contain a claims array")
        proposals: list[ClaimProposal] = []
        for item in data["claims"]:
            if not isinstance(item, dict):
                raise ProviderOutputInvalidError("claim proposal must be an object")
            text = item.get("normalized_text")
            locator = item.get("locator")
            if not isinstance(text, str) or not text.strip() or not isinstance(locator, dict):
                raise ProviderOutputInvalidError("claim proposal requires normalized_text and locator")
            confidence = item.get("confidence")
            if confidence is not None and not isinstance(confidence, (int, float)):
                raise ProviderOutputInvalidError("claim confidence must be numeric or null")
            proposals.append(
                ClaimProposal(
                    normalized_text=text.strip(),
                    locator=locator,
                    confidence=float(confidence) if confidence is not None else None,
                    reason=str(item.get("reason") or ""),
                    metadata={k: v for k, v in item.items() if k not in {"normalized_text", "locator", "confidence", "reason"}},
                )
            )
        return tuple(proposals)


def build_openai_compatible_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider()
