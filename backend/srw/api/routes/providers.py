"""Provider settings routes (ADR-0002 R2, fifth slice).

Three routes: read the provider profiles, update one profile (optionally setting
its API key), and run a reachability probe. Behaviour is identical to the code
that lived inside ``install_full_workbench_routes``; the credential handling
contract lives in :mod:`srw.api.provider_support`, not here.

The route layer never returns a key. It returns `api_key_configured`, which is
the only fact a client needs to decide whether to prompt for one.
"""
from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.api.provider_support import PROVIDER_NAMES, api_key_name, probe_provider, profile_view
from srw.runtime.db.session import v1_session_scope
from srw.runtime.settings import RuntimeSettingsRepository


def provider_routes(*, factory, secrets) -> list[Route]:
    """Bind the provider endpoints to one Core session factory and secret store."""

    async def provider_settings(_r: Request) -> JSONResponse:
        with factory() as session:
            return JSONResponse(profile_view(session, secrets))

    async def provider_update(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if name not in PROVIDER_NAMES:
            raise HTTPException(404)
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            repo = RuntimeSettingsRepository(session)
            current = repo.get_provider_profile(name)
            repo.update_provider_profile(
                name,
                provider_type=s_field(body, "provider_type", current.provider_type),
                model=s_field(body, "model", current.model),
                base_url=s_field(body, "base_url", current.base_url),
                reasoning_effort=s_field(body, "reasoning_effort", current.reasoning_effort),
            )
            if "api_key" in body:
                secrets.set(api_key_name(name), s_field(body, "api_key"))
            return JSONResponse(profile_view(session, secrets))

    async def provider_probe(request: Request) -> JSONResponse:
        # No name whitelist here on purpose: the original handler did not have one,
        # so an unknown provider keeps surfacing as a provider-not-ready failure
        # rather than silently changing into a 404.
        name = request.path_params["name"]
        with factory() as session:
            return JSONResponse(probe_provider(session, secrets, name))

    return [
        Route("/api/v1/settings/providers", provider_settings, methods=["GET"]),
        Route("/api/v1/settings/providers/{name:str}", provider_update, methods=["PATCH"]),
        Route("/api/v1/settings/providers/{name:str}/test", provider_probe, methods=["POST"]),
    ]
