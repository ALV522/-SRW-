from __future__ import annotations

from dataclasses import asdict
from contextlib import asynccontextmanager
from pathlib import Path
import hashlib, json, os, uuid
from time import perf_counter
from typing import Any

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.evidence.pipeline import extract_source_claims, persist_source_claims
from srw.intake.service import CandidateIntakeService
from srw.modules.candidate.commands import confirm_claim
from srw.modules.ai_runs.service import start_ai_run, finish_ai_run, fail_ai_run
from srw.modules.candidate.models import Candidate, Claim, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.release import get_release_state
from srw.modules.decision.commands import make_human_decision, record_verification_note
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.capabilities import CapabilityRegistry
from srw.runtime.db.schema import V1_SCHEMA_REVISION, create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory, v1_session_scope
from srw.runtime.default_capabilities import register_default_lazy_capabilities
from srw.runtime.settings import RuntimeSettingsRepository, SecretStore, SessionSecretStore, FileSecretStore, get_settings_surface
from srw.runtime.local_boundary import LocalBoundaryMiddleware
from srw.runtime.maintenance import cleanup_stale_backup_artifacts
from srw.providers.contracts import ProviderFailureError, ProviderNotReadyError, ProviderOutputInvalidError
from srw.providers.runtime import ProviderRuntime
from srw.privacy.service import build_source_privacy_projection, rebind_privacy_safe_proposals
from srw.evidence.grounding import enrich_source_locator
from srw.surfaces.candidate_workspace import get_candidate_workspace
from srw.surfaces.projects import create_project_with_draft, get_projects_surface
from srw.surfaces.protocol_workspace import get_protocol_workspace
from srw.surfaces.workbench import get_workbench


from srw.kernel.errors import V1RequestValidationError  # re-exported for callers
from srw.api.routes.evidence import evidence_routes
from srw.api.routes.runtime import RuntimeIdentity, runtime_routes
from srw.api.routes.project_authoring import project_authoring_routes
from srw.api.routes.candidate_decision import candidate_decision_routes
from srw.api.request_fields import (
    body_boolean as _bool,
    body_dict as _body,
    body_object as _object,
    body_string as _string,
)


from srw.api.serialization import jsonable as _json


def _choice(body: dict[str, Any], key: str, allowed: set[str], *, default: str) -> str:
    value = _string(body, key, default=default)
    if value not in allowed:
        raise V1RequestValidationError(f"{key} must be one of: {', '.join(sorted(allowed))}")
    return value


def create_v1_app(
    database_url: str,
    *,
    evaluation_policy_revision: str = "policy.v1",
    capability_registry: CapabilityRegistry | None = None,
    secret_store: SecretStore | None = None,
    frontend_dist: str | Path | None = None,
    data_dir: str | Path | None = None,
    knowledge_dir: str | Path | None = None,
) -> Starlette:
    engine = create_v1_engine(database_url)
    create_v1_schema(engine)
    factory = create_v1_session_factory(engine)
    registry = capability_registry or CapabilityRegistry()
    register_default_lazy_capabilities(registry)
    resolved_data_dir = Path(data_dir).resolve() if data_dir is not None else Path.cwd() / "data"
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    startup_cleanup = cleanup_stale_backup_artifacts(resolved_data_dir)
    # Desktop Host ABI: when the WPF host owns the workspace it provides a stable
    # instance/session identity through environment variables. Browser mode keeps
    # generating an ephemeral instance id exactly as before.
    instance_id = os.environ.get("RECRUITMENT_INSTANCE_ID", "").strip() or uuid.uuid4().hex
    runtime_session_id = os.environ.get("RECRUITMENT_SESSION_ID", "").strip() or f"session-{uuid.uuid4().hex[:16]}"
    runtime_session_token = os.environ.get("RECRUITMENT_SESSION_TOKEN", "").strip()
    runtime_mode = os.environ.get("RECRUITMENT_RUNTIME_MODE", "browser").strip() or "browser"
    edition = os.environ.get("RECRUITMENT_EDITION", "web").strip() or "web"
    release = get_release_state()
    release_id = os.environ.get("RECRUITMENT_RELEASE_ID", "").strip() or str(release["version"])
    data_dir_identity = hashlib.sha256(os.path.normcase(str(resolved_data_dir)).encode("utf-8")).hexdigest()
    resolved_knowledge_dir = Path(knowledge_dir).resolve() if knowledge_dir is not None else Path.cwd() / "knowledge" / "active"
    secrets = secret_store or FileSecretStore(resolved_data_dir / "provider_secrets.json")

    async def health_live(_request: Request) -> Response:
        return JSONResponse({"status": "live"})

    async def health_ready(_request: Request) -> Response:
        with factory() as session:
            session.connection()
        return JSONResponse({"status": "ready", "schema_revision": V1_SCHEMA_REVISION})

    async def v1_info(_request: Request) -> Response:
        return JSONResponse({
            "product": "SRW",
            "surface": "v1-core",
            "version": release["version"],
            "schema_revision": V1_SCHEMA_REVISION,
            "evaluation_policy_revision": evaluation_policy_revision,
            "instance_id": instance_id,
            "data_dir_identity": data_dir_identity,
        })

    async def workbench(_request: Request) -> Response:
        with factory() as session:
            return JSONResponse(_json(get_workbench(session, evaluation_policy_revision=evaluation_policy_revision)))

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

    runtime_identity = RuntimeIdentity(
        release=release, instance_id=instance_id, release_id=release_id,
        runtime_session_id=runtime_session_id, runtime_mode=runtime_mode,
        edition=edition, runtime_session_token=runtime_session_token,
        data_dir_identity=data_dir_identity, knowledge_dir=resolved_knowledge_dir,
    )
    routes = [
        Route("/health/live", health_live, methods=["GET"]),
        Route("/health/ready", health_ready, methods=["GET"]),
        Route("/api/v1/info", v1_info, methods=["GET"]),
        *runtime_routes(factory=factory, identity=runtime_identity),
        Route("/api/v1/workbench", workbench, methods=["GET"]),
        *project_authoring_routes(factory=factory),
        Route("/api/v1/settings", settings, methods=["GET"]),
        Route("/api/v1/settings/provider", update_provider_settings, methods=["PATCH"]),
        Route("/api/v1/settings/capabilities/{name:str}", update_capability_policy, methods=["PATCH"]),
        *evidence_routes(factory=factory, registry=registry, secrets=secrets, data_dir=resolved_data_dir),
        *candidate_decision_routes(factory=factory, evaluation_policy_revision=evaluation_policy_revision),
    ]

    def error_response(exc: Exception, *, status_code: int, code: str) -> Response:
        return JSONResponse({"detail": str(exc), "error": {"code": code}}, status_code=status_code)

    async def not_found_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=404, code="not_found")

    async def invariant_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=409, code="invariant_conflict")

    async def validation_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=422, code="invalid_request")

    async def provider_not_ready_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=409, code="provider_not_ready")

    async def provider_failure_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=502, code="provider_failure")

    async def provider_output_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=422, code="provider_output_invalid")

    @asynccontextmanager
    async def _app_lifespan(_app: Starlette):
        try:
            yield
        finally:
            # SQLite keeps file handles in pooled connections even after each
            # request Session closes. Disposing the application-owned Engine is
            # required for Windows to delete/move its workspace and test DBs.
            engine.dispose()

    app = Starlette(
        lifespan=_app_lifespan,
        routes=routes,
        exception_handlers={
            V1NotFoundError: not_found_handler,
            V1InvariantError: invariant_handler,
            V1RequestValidationError: validation_handler,
            ProviderNotReadyError: provider_not_ready_handler,
            ProviderFailureError: provider_failure_handler,
            ProviderOutputInvalidError: provider_output_handler,
        },
    )

    app.add_middleware(LocalBoundaryMiddleware)

    from srw.api.fullworkbench import install_full_workbench_routes
    database_path = Path(str(engine.url.database)).resolve() if engine.url.database and str(engine.url.database) != ":memory:" else (resolved_data_dir / "srw_v1.db")
    install_full_workbench_routes(
        app, factory, registry, secrets,
        data_dir=resolved_data_dir, knowledge_dir=resolved_knowledge_dir, database_path=database_path,
        frontend_dist=Path(frontend_dist).resolve() if frontend_dist is not None else None,
        evaluation_policy_revision=evaluation_policy_revision,
    )
    from srw.api.governance import install_governance_routes
    from srw.api.ranking import install_ranking_routes
    from srw.api.operations import install_operations_routes
    install_governance_routes(app, factory)
    install_ranking_routes(app, factory, evaluation_policy_revision=evaluation_policy_revision)
    install_operations_routes(app, factory, evaluation_policy_revision=evaluation_policy_revision)
    from srw.api.capability_recovery import install_capability_recovery_routes
    install_capability_recovery_routes(app, factory, data_dir=resolved_data_dir, evaluation_policy_revision=evaluation_policy_revision)
    from srw.api.capability_recovery06 import install_capability_recovery06_routes
    install_capability_recovery06_routes(app, factory, data_dir=resolved_data_dir, knowledge_dir=resolved_knowledge_dir)
    from srw.api.capability_recovery07 import install_capability_recovery07_routes
    install_capability_recovery07_routes(app, factory)
    from srw.api.project_portability import install_project_portability_routes
    install_project_portability_routes(app, factory, data_dir=resolved_data_dir)

    if frontend_dist is not None:
        dist = Path(frontend_dist).resolve()
        index = dist / "index.html"
        if index.is_file():
            async def v1_frontend(request: Request) -> Response:
                asset_path = request.path_params.get("asset_path", "")
                requested = (dist / asset_path).resolve() if asset_path else index
                try:
                    requested.relative_to(dist)
                except ValueError:
                    return FileResponse(index)
                if requested.is_file():
                    return FileResponse(requested)
                return FileResponse(index)

            # The legacy 0.8.x WPF Host navigates to the origin root. Keep /v1 as
            # the canonical browser surface, but serve the same index at / so the
            # inherited native Host can remain byte-identical.
            app.routes.append(Route("/", v1_frontend, methods=["GET"]))
            app.routes.append(Route("/v1", v1_frontend, methods=["GET"]))
            app.routes.append(Route("/v1/{asset_path:path}", v1_frontend, methods=["GET"]))

    app.state.shutdown_callback = None
    app.state.startup_cleanup = startup_cleanup
    app.state.runtime_identity = {
        "instance_id": instance_id, "session_id": runtime_session_id, "release_id": release_id,
        "runtime": runtime_mode, "edition": edition,
    }
    return app
