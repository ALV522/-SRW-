"""Settings and capability-policy routes (ADR-0002 R2, fourteenth slice).

Three routes that read and change how the Core behaves at runtime: the settings
surface, the provider connection and the on-demand policy for OCR/ASR.

Behaviour is identical to the code that lived in ``create_v1_app``. Two properties
are easy to break in a move and are pinned by tests:

* the settings surface is returned through ``get_settings_surface``, which reports
  whether a key is configured but never returns the key itself;
* disabling a capability policy both persists the policy and unloads the capability
  from the registry, so a disabled provider cannot keep serving from memory.

``_choice`` moves to :mod:`srw.api.request_fields` as ``body_choice``: without it
this module would have to re-implement the same 422 message, and two copies drift.
"""
from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from srw.api.request_fields import body_choice as _choice, body_dict as _body, body_string as _string
from srw.api.serialization import jsonable as _json
from srw.runtime.db.session import v1_session_scope
from srw.runtime.settings import RuntimeSettingsRepository, get_settings_surface


def settings_routes(*, factory, registry, secrets) -> list[Route]:
    """Bind the settings endpoints to one Core session factory and runtime."""

    async def settings(_request: Request) -> Response:
        with factory() as session:
            return JSONResponse(_json(get_settings_surface(session, registry=registry, secrets=secrets)))

    async def update_provider_settings(request: Request) -> Response:
        body = await _body(request)
        provider_type = _choice(body, "provider_type", {"deepseek", "openai_compatible"}, default="deepseek")
        reasoning_effort = _choice(body, "reasoning_effort", {"low", "medium", "high"}, default="medium")
        with v1_session_scope(factory) as session:
            RuntimeSettingsRepository(session).update_provider(
                provider_type=provider_type,
                model=_string(body, "model", default=""),
                base_url=_string(body, "base_url", default=""),
                reasoning_effort=reasoning_effort,
            )
            if "api_key" in body:
                secrets.set("provider_api_key", _string(body, "api_key", default=""))
            return JSONResponse(_json(get_settings_surface(session, registry=registry, secrets=secrets)))

    async def update_capability_policy(request: Request) -> Response:
        name = request.path_params["name"]
        if name not in {"ocr", "asr"}:
            raise HTTPException(status_code=404, detail="unknown capability")
        body = await _body(request)
        policy = _choice(body, "policy", {"on_demand", "disabled"}, default="on_demand")
        with v1_session_scope(factory) as session:
            RuntimeSettingsRepository(session).set_capability_policy(name, policy)
            if policy == "disabled":
                registry.unload(name)
            return JSONResponse(_json(get_settings_surface(session, registry=registry, secrets=secrets)))

    return [
        Route("/api/v1/settings", settings, methods=["GET"]),
        Route("/api/v1/settings/provider", update_provider_settings, methods=["PATCH"]),
        Route("/api/v1/settings/capabilities/{name:str}", update_capability_policy, methods=["PATCH"]),
    ]
