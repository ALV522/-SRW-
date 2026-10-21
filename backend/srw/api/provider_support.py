"""Provider configuration support shared by the HTTP layer.

`profile_view`, `api_key_name` and `probe_provider` used to be closures inside
`install_full_workbench_routes`. They are needed by the provider settings routes
*and* by the OCR/ASR byte helpers that stay in the aggregate, so they cannot live
inside one route module without either a cycle or a duplicated credential lookup.

Security contract, deliberately centralised here:

* a provider profile view exposes only `api_key_configured` (a boolean) and the
  secret backend's persistence mode - never the key itself, never a prefix or
  length that would narrow a brute-force search;
* the key is read from `SecretStore` only when actually calling a provider;
* a probe failure is re-raised as `ProviderFailureError` without echoing the key
  or the Authorization header.

`convergence_tests/test_provider_routes.py` asserts the first point against the
real HTTP surface.
"""
from __future__ import annotations

import base64
import io
import wave
from typing import Any

from srw.providers.contracts import ProviderFailureError, ProviderNotReadyError
from srw.runtime.settings import RuntimeSettingsRepository

PROVIDER_NAMES = ("text_ai", "ocr", "asr")


def httpx_module():
    try:
        import httpx
    except ImportError as exc:
        raise ProviderNotReadyError("httpx provider pack is unavailable") from exc
    return httpx


def api_key_name(name: str) -> str:
    return "provider_api_key" if name == "text_ai" else f"provider_{name}_api_key"


def profile_view(session, secrets) -> dict[str, Any]:
    repo = RuntimeSettingsRepository(session)
    profiles = {}
    for name in PROVIDER_NAMES:
        profile = repo.get_provider_profile(name)
        profiles[name] = {
            "name": name,
            "provider_type": profile.provider_type,
            "model": profile.model,
            "base_url": profile.base_url,
            "reasoning_effort": profile.reasoning_effort,
            "api_key_configured": secrets.configured(api_key_name(name)),
        }
    return {"profiles": profiles, "secret_persistence": secrets.persistence}


def probe_provider(session, secrets, name: str) -> dict[str, Any]:
    repo = RuntimeSettingsRepository(session)
    profile = repo.get_provider_profile(name)
    key = secrets.get(api_key_name(name))
    if not key:
        raise ProviderNotReadyError(f"{name} API key is not configured")
    httpx = httpx_module()
    base = profile.base_url.rstrip("/")
    try:
        with httpx.Client(timeout=30.0) as client:
            if name == "asr":
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(8000)
                    wav.writeframes(b"\x00\x00" * 800)
                uri = "data:audio/wav;base64," + base64.b64encode(buffer.getvalue()).decode()
                response = client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": profile.model,
                          "messages": [{"role": "user", "content": [
                              {"type": "input_audio", "input_audio": {"data": uri}}]}],
                          "stream": False, "asr_options": {"enable_itn": False}},
                )
            elif name == "ocr":
                # 1x1 valid PNG: endpoint reachability/model authentication probe.
                # Real OCR is tested with user material.
                png = base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
                uri = "data:image/png;base64," + base64.b64encode(png).decode()
                response = client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": profile.model,
                          "messages": [{"role": "user", "content": [
                              {"type": "text", "text": "Respond with OK."},
                              {"type": "image_url", "image_url": {"url": uri}}]}],
                          "max_tokens": 8},
                )
            else:
                response = client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": profile.model,
                          "messages": [{"role": "user", "content": "Reply exactly OK"}],
                          "max_tokens": 8},
                )
            response.raise_for_status()
        return {"ok": True, "profile": name, "model": profile.model}
    except Exception as exc:
        raise ProviderFailureError(f"{name} capability probe failed: {exc}") from exc
