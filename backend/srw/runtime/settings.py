from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from srw.kernel.clock import utc_now
from srw.runtime.capabilities import CapabilityRegistry
from srw.runtime.db.base import V1Base


class RuntimeSetting(V1Base):
    __tablename__ = "runtime_setting"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)




@dataclass(frozen=True, slots=True)
class ProviderProfile:
    name: str
    provider_type: str
    model: str
    base_url: str
    reasoning_effort: str = "medium"


_PROVIDER_DEFAULTS = {
    "text_ai": ProviderProfile("text_ai", "deepseek", "deepseek-v4-flash", "https://api.deepseek.com", "medium"),
    "ocr": ProviderProfile("ocr", "openai_compatible", "qwen3.5-ocr", "https://dashscope.aliyuncs.com/compatible-mode/v1", "medium"),
    "asr": ProviderProfile("asr", "openai_compatible", "qwen3-asr-flash", "https://dashscope.aliyuncs.com/compatible-mode/v1", "medium"),
}

@dataclass(frozen=True, slots=True)
class ProviderPreferences:
    provider_type: str = "deepseek"
    model: str = ""
    base_url: str = "https://api.deepseek.com"
    reasoning_effort: str = "medium"


@dataclass(frozen=True, slots=True)
class ProviderSettingsView:
    provider_type: str
    model: str
    base_url: str
    reasoning_effort: str
    api_key_configured: bool
    secret_persistence: str
    runtime_available: bool
    runtime_loaded: bool


@dataclass(frozen=True, slots=True)
class CapabilitySettingsView:
    name: str
    label: str
    available: bool
    loaded: bool
    policy: str


@dataclass(frozen=True, slots=True)
class SettingsSurface:
    provider: ProviderSettingsView
    capabilities: tuple[CapabilitySettingsView, ...]


class SecretStore(Protocol):
    persistence: str
    def set(self, key: str, value: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def configured(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class SessionSecretStore:
    """Process-memory secret store used until Desktop Host wires OS credential storage."""
    persistence = "session_only"

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        if value:
            self._values[key] = value
        else:
            self._values.pop(key, None)

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def configured(self, key: str) -> bool:
        return bool(self._values.get(key))

    def delete(self, key: str) -> None:
        self._values.pop(key, None)


class FileSecretStore:
    """Portable local secret store. Secrets stay in the local data directory and are excluded from diagnostics/backups."""
    persistence = "portable_local_file"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _write(self, values: dict[str, str]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(values, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def set(self, key: str, value: str) -> None:
        values = self._read()
        if value: values[key] = value
        else: values.pop(key, None)
        self._write(values)

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def configured(self, key: str) -> bool:
        return bool(self.get(key))

    def delete(self, key: str) -> None:
        values = self._read(); values.pop(key, None); self._write(values)


class RuntimeSettingsRepository:
    model = RuntimeSetting

    def __init__(self, session: Session) -> None:
        self.session = session

    def _get(self, key: str, default):
        row = self.session.get(RuntimeSetting, key)
        if row is None:
            return default
        try:
            return json.loads(row.value_json)
        except json.JSONDecodeError:
            return default

    def _set(self, key: str, value) -> None:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        row = self.session.get(RuntimeSetting, key)
        if row is None:
            self.session.add(RuntimeSetting(key=key, value_json=encoded))
        else:
            row.value_json = encoded
        self.session.flush()

    def get_provider(self) -> ProviderPreferences:
        data = self._get("provider.preferences", None)
        if data is None:
            profile = self.get_provider_profile("text_ai")
            return ProviderPreferences(
                provider_type=profile.provider_type, model=profile.model, base_url=profile.base_url,
                reasoning_effort=profile.reasoning_effort,
            )
        defaults = ProviderPreferences()
        return ProviderPreferences(
            provider_type=str(data["provider_type"]) if "provider_type" in data else defaults.provider_type,
            model=str(data["model"]) if "model" in data else defaults.model,
            base_url=str(data["base_url"]) if "base_url" in data else defaults.base_url,
            reasoning_effort=str(data["reasoning_effort"]) if "reasoning_effort" in data else defaults.reasoning_effort,
        )

    def update_provider(self, *, provider_type: str, model: str, base_url: str, reasoning_effort: str) -> ProviderPreferences:
        provider_type = provider_type.strip()
        if provider_type not in {"deepseek", "openai_compatible"}:
            raise ValueError("unsupported provider type")
        reasoning_effort = reasoning_effort.strip() or "medium"
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("unsupported reasoning effort")
        value = {
            "provider_type": provider_type,
            "model": model.strip(),
            "base_url": base_url.strip(),
            "reasoning_effort": reasoning_effort,
        }
        self._set("provider.preferences", value)
        self._set("provider.profile.text_ai", {"provider_type": provider_type, "model": model.strip(), "base_url": base_url.strip(), "reasoning_effort": reasoning_effort})
        return self.get_provider()

    def get_provider_profile(self, name: str) -> ProviderProfile:
        if name not in _PROVIDER_DEFAULTS:
            raise ValueError(f"unknown provider profile: {name}")
        default = _PROVIDER_DEFAULTS[name]
        data = self._get(f"provider.profile.{name}", {})
        return ProviderProfile(
            name=name,
            provider_type=str(data["provider_type"]) if "provider_type" in data else default.provider_type,
            model=str(data["model"]) if "model" in data else default.model,
            base_url=str(data["base_url"]) if "base_url" in data else default.base_url,
            reasoning_effort=str(data["reasoning_effort"]) if "reasoning_effort" in data else default.reasoning_effort,
        )

    def update_provider_profile(self, name: str, *, provider_type: str, model: str, base_url: str, reasoning_effort: str = "medium") -> ProviderProfile:
        if name not in _PROVIDER_DEFAULTS:
            raise ValueError(f"unknown provider profile: {name}")
        if provider_type not in {"deepseek", "openai_compatible"}:
            raise ValueError("unsupported provider type")
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("unsupported reasoning effort")
        value = {
            "provider_type": provider_type, "model": model.strip(), "base_url": base_url.strip(),
            "reasoning_effort": reasoning_effort,
        }
        self._set(f"provider.profile.{name}", value)
        if name == "text_ai":
            self._set("provider.preferences", value)
        return self.get_provider_profile(name)

    def get_capability_policy(self, name: str) -> str:
        return str(self._get(f"capability.{name}.policy", "on_demand"))

    def set_capability_policy(self, name: str, policy: str) -> None:
        if policy not in {"on_demand", "disabled"}:
            raise ValueError("capability policy must be on_demand or disabled")
        self._set(f"capability.{name}.policy", policy)


def get_settings_surface(session: Session, *, registry: CapabilityRegistry, secrets: SecretStore) -> SettingsSurface:
    repo = RuntimeSettingsRepository(session)
    provider = repo.get_provider()
    names = (("ocr", "OCR 文字识别"), ("asr", "ASR 语音转写"))
    capabilities = tuple(
        CapabilitySettingsView(
            name=name,
            label=label,
            available=registry.available(name),
            loaded=registry.loaded(name),
            policy=repo.get_capability_policy(name),
        )
        for name, label in names
    )
    return SettingsSurface(
        provider=ProviderSettingsView(
            provider_type=provider.provider_type,
            model=provider.model,
            base_url=provider.base_url,
            reasoning_effort=provider.reasoning_effort,
            api_key_configured=secrets.configured("provider_api_key"),
            secret_persistence=secrets.persistence,
            runtime_available=registry.available(f"provider.{provider.provider_type}"),
            runtime_loaded=registry.loaded(f"provider.{provider.provider_type}"),
        ),
        capabilities=capabilities,
    )

class CapabilityManager:
    """Policy-aware gateway. Callers must use this rather than resolving heavy capabilities directly."""
    def __init__(self, session: Session, registry: CapabilityRegistry) -> None:
        self.session = session
        self.registry = registry

    def resolve(self, name: str):
        policy = RuntimeSettingsRepository(self.session).get_capability_policy(name)
        if policy == "disabled":
            raise RuntimeError(f"capability disabled: {name}")
        return self.registry.resolve(name)
