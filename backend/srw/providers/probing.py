"""Provider-facing capability operations: settings projection, probes, OCR and ASR calls.

These are domain-level functions: they take an open SQLAlchemy session plus a SecretStore,
perform the provider HTTP call, and raise the provider contract errors. HTTP adapters must
stay thin (validation, serialization, error mapping only) and call into this module.
"""
from __future__ import annotations

import base64
import io
import wave
from typing import Any

from srw.providers.contracts import (
    ProviderFailureError,
    ProviderNotReadyError,
    ProviderOutputInvalidError,
)
from srw.runtime.settings import RuntimeSettingsRepository

ASR_MAX_INLINE_BYTES = 10 * 1024 * 1024


def httpx_client_module():
    """Return the httpx module, or fail closed when the provider pack is unavailable."""
    try:
        import httpx
    except ImportError as exc:
        raise ProviderNotReadyError("httpx provider pack is unavailable") from exc
    return httpx


def provider_secret_key(name: str) -> str:
    """Map a provider profile name to its secret-store key (text_ai keeps the legacy key)."""
    return "provider_api_key" if name == "text_ai" else f"provider_{name}_api_key"


def provider_profile_view(session, secrets) -> dict[str, Any]:
    """Project the text_ai/ocr/asr profiles with key configuration and persistence status."""
    repo = RuntimeSettingsRepository(session)
    profiles: dict[str, Any] = {}
    for name in ("text_ai", "ocr", "asr"):
        p = repo.get_provider_profile(name)
        profiles[name] = {
            "name": name,
            "provider_type": p.provider_type,
            "model": p.model,
            "base_url": p.base_url,
            "reasoning_effort": p.reasoning_effort,
            "api_key_configured": secrets.configured(provider_secret_key(name)),
        }
    return {"profiles": profiles, "secret_persistence": secrets.persistence}


def probe_provider(session, secrets, name: str) -> dict[str, Any]:
    """Send one minimal reachability/authentication probe for a provider profile.

    text_ai posts a plain chat completion; ocr posts a 1x1 valid PNG (endpoint reachability
    and model authentication only - real OCR is exercised with user material); asr posts a
    short synthetic 8 kHz mono WAV. No candidate content is ever sent.
    """
    repo = RuntimeSettingsRepository(session)
    p = repo.get_provider_profile(name)
    key = secrets.get(provider_secret_key(name))
    if not key:
        raise ProviderNotReadyError(f"{name} API key is not configured")
    httpx = httpx_client_module()
    base = p.base_url.rstrip("/")
    try:
        with httpx.Client(timeout=30.0) as c:
            if name == "asr":
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(8000)
                    w.writeframes(b"\x00\x00" * 800)
                uri = "data:audio/wav;base64," + base64.b64encode(buffer.getvalue()).decode()
                r = c.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": p.model,
                        "messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": uri}}]}],
                        "stream": False,
                        "asr_options": {"enable_itn": False},
                    },
                )
            elif name == "ocr":
                png = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
                uri = "data:image/png;base64," + base64.b64encode(png).decode()
                r = c.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": p.model,
                        "messages": [{"role": "user", "content": [{"type": "text", "text": "Respond with OK."}, {"type": "image_url", "image_url": {"url": uri}}]}],
                        "max_tokens": 8,
                    },
                )
            else:
                r = c.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": p.model, "messages": [{"role": "user", "content": "Reply exactly OK"}], "max_tokens": 8},
                )
            r.raise_for_status()
        return {"ok": True, "profile": name, "model": p.model}
    except Exception as exc:
        raise ProviderFailureError(f"{name} capability probe failed: {exc}") from exc


def ocr_image_bytes(session, secrets, raw: bytes, media_type: str) -> str:
    """Extract visible text from image bytes through the configured OCR provider."""
    p = RuntimeSettingsRepository(session).get_provider_profile("ocr")
    key = secrets.get(provider_secret_key("ocr"))
    if not key:
        raise ProviderNotReadyError("OCR API key is not configured")
    uri = f"data:{media_type};base64," + base64.b64encode(raw).decode()
    httpx = httpx_client_module()
    try:
        with httpx.Client(timeout=90.0) as c:
            r = c.post(
                p.base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": p.model,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": "Extract all visible text faithfully. Return plain text only."}, {"type": "image_url", "image_url": {"url": uri}}]}],
                },
            )
            r.raise_for_status()
            body = r.json()
            text = str(body["choices"][0]["message"]["content"]).strip()
            if not text:
                raise ValueError("empty OCR output")
            return text
    except ProviderNotReadyError:
        raise
    except Exception as exc:
        raise ProviderFailureError(f"OCR request failed: {exc}") from exc


def transcribe_audio_bytes(session, secrets, raw: bytes, filename: str, media_type: str) -> str:
    """Transcribe audio bytes through the configured ASR provider.

    ``filename`` is accepted for call-site parity and future file-transcription profiles;
    the current inline payload contract does not use it. Payloads above
    ``ASR_MAX_INLINE_BYTES`` are rejected before any network call.
    """
    p = RuntimeSettingsRepository(session).get_provider_profile("asr")
    key = secrets.get(provider_secret_key("asr"))
    if not key:
        raise ProviderNotReadyError("ASR API key is not configured")
    if len(raw) > ASR_MAX_INLINE_BYTES:
        raise ProviderOutputInvalidError(
            "qwen3-asr-flash accepts at most 10 MB; use a long-audio/file-transcription profile"
        )
    data_uri = f"data:{media_type or 'audio/wav'};base64," + base64.b64encode(raw).decode()
    httpx = httpx_client_module()
    try:
        with httpx.Client(timeout=180.0) as c:
            r = c.post(
                p.base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": p.model,
                    "messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}]}],
                    "stream": False,
                    "asr_options": {"enable_itn": False},
                },
            )
            r.raise_for_status()
            body = r.json()
            text = str(body["choices"][0]["message"]["content"] or "").strip()
            if not text:
                raise ValueError("empty ASR output")
            return text
    except ProviderNotReadyError:
        raise
    except ProviderOutputInvalidError:
        raise
    except Exception as exc:
        raise ProviderFailureError(f"ASR request failed: {exc}") from exc
