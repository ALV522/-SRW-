"""Provider probing/OCR/ASR domain operations, extracted from the HTTP layer.

All network calls go through a fake httpx client; no real provider is contacted and no
candidate content is used. The HTTP boundary is checked once through create_v1_app.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.providers import probing
from srw.providers.contracts import (
    ProviderFailureError,
    ProviderNotReadyError,
    ProviderOutputInvalidError,
)
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory
from srw.runtime.settings import RuntimeSettingsRepository


class _FakeSecrets:
    """In-memory SecretStore stand-in (set/get/configured/delete + persistence)."""

    persistence = "session_only"

    def __init__(self, values=None):
        self.values = dict(values or {})

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def configured(self, key):
        return bool(self.values.get(key))

    def delete(self, key):
        self.values.pop(key, None)


class _FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler, timeout=None):
        self._handler = handler
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        return self._handler(url, kwargs)


class _FakeHttpx:
    def __init__(self, handler):
        self._handler = handler
        self.last_client = None

    def Client(self, timeout=None):
        self.last_client = _FakeClient(self._handler, timeout)
        return self.last_client


def _chat_content(text):
    return {"choices": [{"message": {"content": text}}]}


class ProviderProbingDomainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        engine = create_v1_engine(f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}")
        self.addCleanup(engine.dispose)
        create_v1_schema(engine)
        self.factory = create_v1_session_factory(engine)

    def _configure_profile(self, name, *, base_url="https://provider.invalid/v1", model="synthetic-model"):
        with self.factory.begin() as session:
            RuntimeSettingsRepository(session).update_provider_profile(
                name, provider_type="openai_compatible", model=model, base_url=base_url
            )

    def _install_fake_httpx(self, handler):
        """Patch the module-level httpx accessor; returns the fake for timeout assertions."""
        fake = _FakeHttpx(handler)
        original = probing.httpx_client_module
        self.addCleanup(setattr, probing, "httpx_client_module", original)
        probing.httpx_client_module = lambda: fake
        return fake

    def test_provider_secret_key_mapping(self):
        self.assertEqual(probing.provider_secret_key("text_ai"), "provider_api_key")
        self.assertEqual(probing.provider_secret_key("ocr"), "provider_ocr_api_key")
        self.assertEqual(probing.provider_secret_key("asr"), "provider_asr_api_key")

    def test_profile_view_projects_three_profiles_and_key_status(self):
        secrets = _FakeSecrets({"provider_api_key": "k-text", "provider_ocr_api_key": "k-ocr"})
        with self.factory() as session:
            view = probing.provider_profile_view(session, secrets)
        self.assertEqual(set(view["profiles"]), {"text_ai", "ocr", "asr"})
        self.assertTrue(view["profiles"]["text_ai"]["api_key_configured"])
        self.assertTrue(view["profiles"]["ocr"]["api_key_configured"])
        self.assertFalse(view["profiles"]["asr"]["api_key_configured"])
        self.assertEqual(view["secret_persistence"], "session_only")
        self.assertEqual(view["profiles"]["ocr"]["name"], "ocr")

    def test_probe_requires_api_key(self):
        self._configure_profile("text_ai")
        with self.factory() as session:
            with self.assertRaises(ProviderNotReadyError):
                probing.probe_provider(session, _FakeSecrets(), "text_ai")

    def test_probe_text_ai_posts_expected_request(self):
        self._configure_profile("text_ai", base_url="https://provider.invalid/v1/")
        seen = {}

        def handler(url, kwargs):
            seen["url"] = url
            seen["kwargs"] = kwargs
            return _FakeResponse(_chat_content("OK"))

        self._install_fake_httpx(handler)
        with self.factory() as session:
            result = probing.probe_provider(session, _FakeSecrets({"provider_api_key": "k"}), "text_ai")
        self.assertEqual(result, {"ok": True, "profile": "text_ai", "model": "synthetic-model"})
        self.assertEqual(seen["url"], "https://provider.invalid/v1/chat/completions")
        self.assertEqual(seen["kwargs"]["headers"]["Authorization"], "Bearer k")
        self.assertEqual(seen["kwargs"]["json"]["messages"][0]["content"], "Reply exactly OK")
        self.assertEqual(seen["kwargs"]["json"]["max_tokens"], 8)

    def test_probe_uses_short_timeout(self):
        self._configure_profile("text_ai")
        fake = self._install_fake_httpx(lambda url, kwargs: _FakeResponse(_chat_content("OK")))
        with self.factory() as session:
            probing.probe_provider(session, _FakeSecrets({"provider_api_key": "k"}), "text_ai")
        self.assertEqual(fake.last_client.timeout, 30.0)

    def test_probe_ocr_sends_png_probe_payload(self):
        self._configure_profile("ocr")
        seen = {}

        def handler(url, kwargs):
            seen.update(kwargs)
            return _FakeResponse(_chat_content("OK"))

        self._install_fake_httpx(handler)
        with self.factory() as session:
            result = probing.probe_provider(session, _FakeSecrets({"provider_ocr_api_key": "k"}), "ocr")
        self.assertTrue(result["ok"])
        content = seen["json"]["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "Respond with OK.")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_probe_asr_sends_wav_probe_payload(self):
        self._configure_profile("asr")
        seen = {}

        def handler(url, kwargs):
            seen.update(kwargs)
            return _FakeResponse(_chat_content("OK"))

        self._install_fake_httpx(handler)
        with self.factory() as session:
            result = probing.probe_provider(session, _FakeSecrets({"provider_asr_api_key": "k"}), "asr")
        self.assertTrue(result["ok"])
        payload = seen["json"]
        audio = payload["messages"][0]["content"][0]["input_audio"]["data"]
        self.assertTrue(audio.startswith("data:audio/wav;base64,"))
        self.assertFalse(payload["asr_options"]["enable_itn"])
        self.assertFalse(payload["stream"])

    def test_probe_failure_maps_to_provider_failure(self):
        self._configure_profile("text_ai")
        self._install_fake_httpx(lambda url, kwargs: _FakeResponse(error=RuntimeError("boom")))
        with self.factory() as session:
            with self.assertRaises(ProviderFailureError) as ctx:
                probing.probe_provider(session, _FakeSecrets({"provider_api_key": "k"}), "text_ai")
        self.assertIn("text_ai capability probe failed", str(ctx.exception))

    def test_ocr_requires_api_key(self):
        self._configure_profile("ocr")
        with self.factory() as session:
            with self.assertRaises(ProviderNotReadyError):
                probing.ocr_image_bytes(session, _FakeSecrets(), b"\x89PNG", "image/png")

    def test_ocr_extracts_and_strips_text(self):
        self._configure_profile("ocr")
        seen = {}

        def handler(url, kwargs):
            seen.update(kwargs)
            return _FakeResponse(_chat_content("  extracted resume text  "))

        fake = self._install_fake_httpx(handler)
        with self.factory() as session:
            text = probing.ocr_image_bytes(session, _FakeSecrets({"provider_ocr_api_key": "k"}), b"\x89PNG-bytes", "image/png")
        self.assertEqual(text, "extracted resume text")
        self.assertTrue(seen["json"]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(fake.last_client.timeout, 90.0)

    def test_ocr_empty_output_is_failure(self):
        self._configure_profile("ocr")
        self._install_fake_httpx(lambda url, kwargs: _FakeResponse(_chat_content("   ")))
        with self.factory() as session:
            with self.assertRaises(ProviderFailureError) as ctx:
                probing.ocr_image_bytes(session, _FakeSecrets({"provider_ocr_api_key": "k"}), b"\x89PNG", "image/png")
        self.assertIn("OCR request failed", str(ctx.exception))

    def test_asr_requires_api_key(self):
        self._configure_profile("asr")
        with self.factory() as session:
            with self.assertRaises(ProviderNotReadyError):
                probing.transcribe_audio_bytes(session, _FakeSecrets(), b"RIFF", "clip.wav", "audio/wav")

    def test_asr_rejects_oversize_payload_without_network(self):
        self._configure_profile("asr")

        def handler(url, kwargs):
            raise AssertionError("oversize payload must not reach the network")

        self._install_fake_httpx(handler)
        with self.factory() as session:
            with self.assertRaises(ProviderOutputInvalidError):
                probing.transcribe_audio_bytes(
                    session, _FakeSecrets({"provider_asr_api_key": "k"}),
                    b"\x00" * (10 * 1024 * 1024 + 1), "clip.wav", "audio/wav",
                )

    def test_asr_transcribes_audio(self):
        self._configure_profile("asr")
        seen = {}

        def handler(url, kwargs):
            seen.update(kwargs)
            return _FakeResponse(_chat_content("  transcribed interview  "))

        fake = self._install_fake_httpx(handler)
        with self.factory() as session:
            text = probing.transcribe_audio_bytes(
                session, _FakeSecrets({"provider_asr_api_key": "k"}), b"RIFF-bytes", "clip.wav", "audio/wav"
            )
        self.assertEqual(text, "transcribed interview")
        payload = seen["json"]
        audio = payload["messages"][0]["content"][0]["input_audio"]["data"]
        self.assertTrue(audio.startswith("data:audio/wav;base64,"))
        self.assertEqual(fake.last_client.timeout, 180.0)

    def test_asr_empty_output_is_failure(self):
        self._configure_profile("asr")
        self._install_fake_httpx(lambda url, kwargs: _FakeResponse(_chat_content("")))
        with self.factory() as session:
            with self.assertRaises(ProviderFailureError) as ctx:
                probing.transcribe_audio_bytes(session, _FakeSecrets({"provider_asr_api_key": "k"}), b"RIFF", "clip.wav", "audio/wav")
        self.assertIn("ASR request failed", str(ctx.exception))


class ProviderSettingsHttpBoundaryTests(unittest.TestCase):
    """The thin HTTP adapter still serves the projected provider view end to end."""

    def test_settings_providers_route_returns_profile_view(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            url = f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}"
            app = create_v1_app(
                url,
                data_dir=root / "data",
                knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
                secret_store=_FakeSecrets({"provider_api_key": "k-text"}),
            )
            with TestClient(app) as client:
                response = client.get("/api/v1/settings/providers")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body["profiles"]), {"text_ai", "ocr", "asr"})
        self.assertTrue(body["profiles"]["text_ai"]["api_key_configured"])
        self.assertFalse(body["profiles"]["ocr"]["api_key_configured"])
        self.assertEqual(body["secret_persistence"], "session_only")


if __name__ == "__main__":
    unittest.main()
