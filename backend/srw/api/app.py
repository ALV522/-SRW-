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

from srw.kernel.errors import V1InvariantError, V1NotFoundError, V1RevisionConflict
from srw.evidence.pipeline import extract_source_claims, persist_source_claims
from srw.intake.service import CandidateIntakeService
from srw.modules.candidate.commands import confirm_claim
from srw.modules.ai_runs.service import start_ai_run, finish_ai_run, fail_ai_run
from srw.modules.candidate.models import Candidate, Claim, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.release import get_release_state
from srw.modules.decision.commands import make_human_decision, record_verification_note
from srw.modules.decision.context import get_current_decision_context
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


class V1RequestValidationError(ValueError):
    pass


def _json(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


async def _body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception as exc:  # malformed JSON belongs to the HTTP adapter, not the domain
        raise V1RequestValidationError("request body must be valid JSON") from exc
    if not isinstance(value, dict):
        raise V1RequestValidationError("request body must be an object")
    return value


def _string(body: dict[str, Any], key: str, *, default: str | None = None, required: bool = False) -> str:
    value = body.get(key, default)
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise V1RequestValidationError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise V1RequestValidationError(f"{key} is required")
    return value


def _choice(body: dict[str, Any], key: str, allowed: set[str], *, default: str) -> str:
    value = _string(body, key, default=default)
    if value not in allowed:
        raise V1RequestValidationError(f"{key} must be one of: {', '.join(sorted(allowed))}")
    return value


def _object(body: dict[str, Any], key: str, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    value = body.get(key, default if default is not None else {})
    if not isinstance(value, dict):
        raise V1RequestValidationError(f"{key} must be an object")
    return value


def _bool(body: dict[str, Any], key: str, *, default: bool = False, required: bool = False) -> bool:
    if key not in body:
        if required:
            raise V1RequestValidationError(f"{key} is required")
        return default
    value = body[key]
    if not isinstance(value, bool):
        raise V1RequestValidationError(f"{key} must be a boolean")
    return value


def _if_match_token(request: Request) -> str | None:
    """Optional If-Match precondition (ADR-0003 S2).

    Returns the opaque revision token the client based its edit on, or None
    when the client sent no precondition. The token is compared with the
    current token inside the write transaction; a mismatch raises
    V1RevisionConflict -> HTTP 412 with nothing written.
    """
    header = request.headers.get("if-match") or ""
    token = header.strip()
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        token = token[1:-1]
    return token.strip() or None


def _enforce_if_match(expected: str | None, current: str) -> None:
    """Transaction-scoped precondition check: refuse stale writes before any mutation."""
    if expected is not None and expected != current:
        raise V1RevisionConflict(
            f"if-match {expected!r} does not match current revision {current!r}; reload and retry"
        )


def create_v1_app(
    database_url: str,
    *,
    evaluation_policy_revision: str = "policy.v1",
    capability_registry: CapabilityRegistry | None = None,
    secret_store: SecretStore | None = None,
    frontend_dist: str | Path | None = None,
    data_dir: str | Path | None = None,
    knowledge_dir: str | Path | None = None,
    supervisor_service=None,
    enforce_carrier_sessions: bool = False,
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

    async def runtime_live(_request: Request) -> Response:
        return JSONResponse({
            "status": "live", "product": "SRW", "version": release["version"],
            "instanceId": instance_id, "releaseId": release_id, "sessionId": runtime_session_id,
        })

    async def runtime_ready(_request: Request) -> Response:
        issues: list[str] = []
        try:
            with factory() as session:
                session.connection()
        except Exception as exc:
            issues.append(f"database_not_ready:{type(exc).__name__}")
        knowledge_ready = all((resolved_knowledge_dir / name / "knowledge.db").is_file() for name in ("taxonomy","job_info","competency","market_reference","reference"))
        if not knowledge_ready:
            issues.append("knowledge_not_ready")
        ready = not issues
        return JSONResponse({
            "status": "ready" if ready else "not_ready",
            "version": release["version"],
            "schemaVersion": V1_SCHEMA_REVISION,
            "databaseReady": not any(x.startswith("database_not_ready") for x in issues),
            "knowledgeReady": knowledge_ready,
            "issues": issues,
        }, status_code=200 if ready else 503)

    async def runtime_info(_request: Request) -> Response:
        body = {
            "apiVersion": "v1", "product": "SRW", "version": release["version"],
            "schemaVersion": V1_SCHEMA_REVISION, "runtime": runtime_mode, "edition": edition,
            "instanceId": instance_id, "releaseId": release_id, "sessionId": runtime_session_id,
            "dataScopeId": data_dir_identity,
            "frontend": {"mode": "static_dist"},
            "capabilities": {
                "desktop": runtime_mode == "desktop", "nativeFileDialogs": False,
                "secureSecretStore": False, "notifications": False, "clipboard": True,
                "downloads": True, "externalNavigation": True,
                "gracefulShutdown": True, "lifecycleSessionTokenSupported": True,
                "lifecycleSessionTokenRequired": bool(runtime_session_token),
            },
            "readiness": {"status": "ready"},
        }
        supervisor_service = getattr(app.state, "supervisor_service", None)
        if supervisor_service is not None:
            body["supervisor"] = supervisor_service.status().public_view()
        return JSONResponse(body)

    async def runtime_capabilities(_request: Request) -> Response:
        info = await runtime_info(_request)
        # Avoid reparsing Response internals: keep a concise capability contract.
        return JSONResponse({
            "runtime": runtime_mode, "edition": edition, "desktop": runtime_mode == "desktop",
            "nativeFileDialogs": False, "secureSecretStore": False, "notifications": False,
            "clipboard": True, "downloads": True, "externalNavigation": True,
            "gracefulShutdown": True, "lifecycleSessionTokenSupported": True,
            "lifecycleSessionTokenRequired": bool(runtime_session_token),
        })

    async def runtime_shutdown(request: Request) -> Response:
        if runtime_session_token and request.headers.get("X-SRW-Session", "") != runtime_session_token:
            return JSONResponse({"detail": "运行时会话令牌无效"}, status_code=403)
        callback = getattr(request.app.state, "shutdown_callback", None)
        if callback is None:
            return JSONResponse({"detail": "当前启动方式不支持 Host 安全退出"}, status_code=409)
        return JSONResponse({"status": "shutting_down"}, status_code=202, background=BackgroundTask(callback))

    async def workbench(_request: Request) -> Response:
        with factory() as session:
            return JSONResponse(_json(get_workbench(session, evaluation_policy_revision=evaluation_policy_revision)))

    async def projects(_request: Request) -> Response:
        with factory() as session:
            return JSONResponse(_json(get_projects_surface(session)))

    async def create_project(request: Request) -> Response:
        body = await _body(request)
        with v1_session_scope(factory) as session:
            result = create_project_with_draft(
                session,
                title=_string(body, "title", required=True),
                role_title=_string(body, "role_title", required=True),
                brief_summary=_string(body, "brief_summary", default=""),
            )
            return JSONResponse(_json(result))

    async def fork_protocol_draft(request: Request) -> Response:
        project_id = request.path_params["project_id"]
        with v1_session_scope(factory) as session:
            row = ProtocolRepository(session).fork_current_to_draft(project_id)
            return JSONResponse({"revision_id": row.id, "revision": row.revision, "state": row.state})

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

    async def protocol_workspace(request: Request) -> Response:
        with factory() as session:
            return JSONResponse(_json(get_protocol_workspace(session, request.path_params["project_id"])))

    async def update_protocol(request: Request) -> Response:
        body = await _body(request)
        expected = _if_match_token(request)
        with v1_session_scope(factory) as session:
            repo = ProtocolRepository(session)
            if expected is not None:
                _enforce_if_match(expected, repo.current_token(request.path_params["revision_id"]))
            row = repo.update_draft(
                request.path_params["revision_id"],
                _object(body, "payload"),
                _object(body, "provenance", default={}),
            )
            return JSONResponse(
                {"revision_id": row.id, "revision": row.revision, "state": row.state,
                 "token": f"{row.id}:{row.content_hash}"}
            )

    async def publish_protocol(request: Request) -> Response:
        expected = _if_match_token(request)
        with v1_session_scope(factory) as session:
            repo = ProtocolRepository(session)
            if expected is not None:
                _enforce_if_match(expected, repo.current_token(request.path_params["revision_id"]))
            row = repo.publish(request.path_params["revision_id"])
            return JSONResponse(
                {"revision_id": row.id, "revision": row.revision, "state": row.state,
                 "token": f"{row.id}:{row.content_hash}"}
            )

    async def add_text_candidate_source(request: Request) -> Response:
        body = await _body(request)
        candidate_id = request.path_params["candidate_id"]
        with v1_session_scope(factory) as session:
            service = CandidateIntakeService(session)
            source = service.add_text_source(
                candidate_id,
                _string(body, "text_content", required=True),
                filename=_string(body, "filename", default=""),
                source_kind=_string(body, "source_kind", default="resume") or "resume",
                media_type=_string(body, "media_type", default="text/plain") or "text/plain",
            )
            material_revision_id = None
            if _bool(body, "publish_material", default=False):
                candidate = session.get(Candidate, candidate_id)
                if candidate is None:
                    raise V1NotFoundError(f"candidate not found: {candidate_id}")
                current_ids = get_current_source_ids(session, candidate_id) if candidate.current_material_revision_id else []
                if source.id in current_ids:
                    material_revision_id = candidate.current_material_revision_id
                else:
                    material = MaterialRepository(session).publish_revision(
                        candidate_id,
                        [*current_ids, source.id],
                        provenance={"action": "text_intake", "source_id": source.id},
                    )
                    material_revision_id = material.id
            return JSONResponse({
                "source_id": source.id,
                "candidate_id": source.candidate_id,
                "source_kind": source.source_kind,
                "content_hash": source.content_hash,
                "material_revision_id": material_revision_id,
            })

    async def extract_candidate_evidence(request: Request) -> Response:
        """Compatibility synchronous endpoint with privacy-safe AI execution ledger."""
        body = await _body(request)
        candidate_id = request.path_params["candidate_id"]
        source_id = _string(body, "source_id", required=True)
        runtime = ProviderRuntime(registry=registry, secrets=secrets)
        with v1_session_scope(factory) as session:
            source = session.get(Source, source_id)
            candidate = session.get(Candidate, candidate_id)
            if source is None:
                raise V1NotFoundError(f"source not found: {source_id}")
            if candidate is None:
                raise V1NotFoundError(f"candidate not found: {candidate_id}")
            if source.candidate_id != candidate_id:
                raise V1InvariantError("source belongs to another candidate")
            projection = build_source_privacy_projection(session, source)
            prepared = runtime.prepare_evidence_call(session, source_text=projection.safe_text)
            profile = RuntimeSettingsRepository(session).get_provider_profile("text_ai")
            run = start_ai_run(
                session,
                task_type="evidence_extract",
                project_id=candidate.project_id,
                candidate_id=candidate_id,
                source_id=source_id,
                provider_kind=profile.provider_type,
                model_name=prepared.request.model,
                input_material=projection.safe_text,
                input_safety_meta={
                    "privacy_projection": True,
                    "length_preserved": projection.redaction.length_preserved,
                    "redaction_counts": projection.redaction.counts,
                },
            )
            run_id = run.id
        started = perf_counter()
        try:
            proposals = runtime.execute_evidence_call(prepared)
            proposals = rebind_privacy_safe_proposals(projection, proposals)
        except Exception as exc:
            with v1_session_scope(factory) as session:
                fail_ai_run(
                    session, run_id, exc,
                    latency_ms=int((perf_counter() - started) * 1000),
                    error_code=("provider_output_invalid" if isinstance(exc, ProviderOutputInvalidError) else "provider_failure"),
                )
            raise
        with v1_session_scope(factory) as session:
            source = session.get(Source, source_id)
            if source is None:
                raise V1NotFoundError(f"source not found: {source_id}")
            if source.candidate_id != candidate_id:
                raise V1InvariantError("source belongs to another candidate")
            result = persist_source_claims(session, source_id, proposals)
            finish_ai_run(
                session, run_id, _json(result),
                latency_ms=int((perf_counter() - started) * 1000),
            )
            return JSONResponse(_json(result))

    async def source_content(request: Request) -> Response:
        source_id = request.path_params["source_id"]
        with factory() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise V1NotFoundError(f"source not found: {source_id}")
            import json
            try:
                metadata = json.loads(source.metadata_json or "{}")
            except Exception:
                metadata = {}
            filename = ""
            if isinstance(metadata, dict):
                filename = str(metadata.get("filename") or metadata.get("original_filename") or "")
            return JSONResponse({
                "source_id": source.id, "candidate_id": source.candidate_id,
                "source_kind": source.source_kind, "media_type": source.media_type,
                "has_text": bool(source.text_content.strip()), "text_content": source.text_content,
                "has_blob": bool(source.blob_hash), "filename": filename,
                "file_url": f"/api/v1/sources/{source.id}/file" if source.blob_hash else None,
                "metadata": metadata if isinstance(metadata, dict) else {},
            })

    async def source_file(request: Request) -> Response:
        source_id = request.path_params["source_id"]
        with factory() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise V1NotFoundError(f"source not found: {source_id}")
            if not source.blob_hash:
                raise V1NotFoundError("source has no stored binary file")
            digest = source.blob_hash.strip().lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise V1InvariantError("source blob hash is invalid")
            path = resolved_data_dir / "blobs" / digest[:2] / digest
            if not path.is_file():
                raise V1NotFoundError("source binary file is missing")
            import json
            try:
                metadata = json.loads(source.metadata_json or "{}")
            except Exception:
                metadata = {}
            filename = str(metadata.get("filename") or metadata.get("original_filename") or source_id) if isinstance(metadata, dict) else source_id
            return FileResponse(
                path,
                media_type=source.media_type or "application/octet-stream",
                filename=Path(filename).name or source_id,
                content_disposition_type="inline",
            )

    async def source_page_render(request: Request) -> Response:
        source_id = request.path_params["source_id"]
        page_number = int(request.path_params["page_number"])
        if page_number < 1:
            raise V1InvariantError("page_number must be >= 1")
        try:
            scale = float(request.query_params.get("scale", "1.6"))
        except ValueError as exc:
            raise V1InvariantError("scale must be numeric") from exc
        if not 0.75 <= scale <= 3.0:
            raise V1InvariantError("scale must be between 0.75 and 3.0")
        claim_id = (request.query_params.get("claim_id") or "").strip()
        with factory() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise V1NotFoundError(f"source not found: {source_id}")
            if (source.media_type or "").lower() != "application/pdf":
                raise V1InvariantError("page rendering is only available for PDF sources")
            if not source.blob_hash:
                raise V1NotFoundError("source has no stored binary file")
            digest = source.blob_hash.strip().lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise V1InvariantError("source blob hash is invalid")
            path = resolved_data_dir / "blobs" / digest[:2] / digest
            if not path.is_file():
                raise V1NotFoundError("source binary file is missing")
            locator = None
            if claim_id:
                claim = session.get(Claim, claim_id)
                if claim is None:
                    raise V1NotFoundError(f"claim not found: {claim_id}")
                if claim.source_id != source.id:
                    raise V1InvariantError("claim belongs to another source")
                try:
                    raw_locator = json.loads(claim.source_locator_json or "{}")
                except Exception:
                    raw_locator = {}
                locator = enrich_source_locator(source, raw_locator)
                if locator is None:
                    raise V1InvariantError("claim grounding no longer matches its source")
                grounded_page = locator.get("page")
                if isinstance(grounded_page, int) and grounded_page != page_number:
                    raise V1InvariantError("requested page does not match claim grounding")
            try:
                import fitz
            except ImportError as exc:
                raise V1InvariantError("PyMuPDF is unavailable for PDF page rendering") from exc
            try:
                with fitz.open(path) as document:
                    if page_number > len(document):
                        raise V1NotFoundError(f"PDF page not found: {page_number}")
                    page = document.load_page(page_number - 1)
                    highlighted = False
                    if locator and isinstance(locator.get("bbox"), list) and len(locator["bbox"]) == 4:
                        try:
                            rect = fitz.Rect(*[float(x) for x in locator["bbox"]])
                            if rect.is_valid and not rect.is_empty:
                                page.draw_rect(rect, color=(0.85, 0.15, 0.15), width=1.6, fill=(1.0, 0.92, 0.2), fill_opacity=0.24, overlay=True)
                                highlighted = True
                        except Exception:
                            highlighted = False
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    png = pix.tobytes("png")
            except V1NotFoundError:
                raise
            except Exception as exc:
                raise V1InvariantError(f"PDF page rendering failed: {exc}") from exc
            return Response(
                png,
                media_type="image/png",
                headers={
                    "Cache-Control": "no-store",
                    "X-SRW-Source-Id": source.id,
                    "X-SRW-Page": str(page_number),
                    "X-SRW-Grounding-Highlight": "1" if highlighted else "0",
                },
            )

    async def source_scoring_view(request: Request) -> Response:
        source_id = request.path_params["source_id"]
        with factory() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise V1NotFoundError(f"source not found: {source_id}")
            projection = build_source_privacy_projection(session, source)
            return JSONResponse({
                "source_id": source.id, "candidate_id": source.candidate_id,
                "text_content": projection.safe_text,
                "redaction_counts": projection.redaction.counts,
                "redaction_spans": [{"kind": x.kind, "start": x.start, "end": x.end} for x in projection.redaction.spans],
                "length_preserved": projection.redaction.length_preserved,
                "remote_provider_safe": True,
            })

    async def claim_grounding(request: Request) -> Response:
        claim_id = request.path_params["claim_id"]
        with factory() as session:
            claim = session.get(Claim, claim_id)
            if claim is None:
                raise V1NotFoundError(f"claim not found: {claim_id}")
            source = session.get(Source, claim.source_id)
            if source is None:
                raise V1NotFoundError(f"source not found: {claim.source_id}")
            import json
            try:
                locator = json.loads(claim.source_locator_json or "{}")
            except Exception:
                locator = {}
            enriched = enrich_source_locator(source, locator)
            if enriched is None:
                raise V1InvariantError("claim grounding no longer matches its source")
            return JSONResponse({"claim_id": claim.id, "source_id": source.id, "locator": enriched})

    async def review_claim(request: Request) -> Response:
        body = await _body(request)
        with v1_session_scope(factory) as session:
            row = confirm_claim(
                session,
                request.path_params["claim_id"],
                accepted=_bool(body, "accepted", required=True),
                actor=_string(body, "actor", default="human") or "human",
            )
            return JSONResponse({
                "claim_id": row.id,
                "confirmation_state": row.confirmation_state,
                "authority": row.authority,
            })

    async def candidate_workspace(request: Request) -> Response:
        with factory() as session:
            value = get_candidate_workspace(
                session,
                request.path_params["candidate_id"],
                evaluation_policy_revision=evaluation_policy_revision,
            )
            return JSONResponse(_json(value))

    async def candidate_assessment(request: Request) -> Response:
        with factory() as session:
            return JSONResponse(get_candidate_assessment(session,request.path_params["candidate_id"],evaluation_policy_revision=evaluation_policy_revision))

    async def verify(request: Request) -> Response:
        body = await _body(request)
        candidate_id = request.path_params["candidate_id"]
        expected = _if_match_token(request)
        with v1_session_scope(factory) as session:
            if expected is not None:
                current = get_current_decision_context(
                    session, candidate_id, evaluation_policy_revision=evaluation_policy_revision
                ).hash
                _enforce_if_match(expected, current)
            record_verification_note(
                session,
                candidate_id,
                _string(body, "criterion_key", required=True),
                note=_string(body, "note", required=True),
                status=_string(body, "status", required=True),
                evidence_level=_string(body, "evidence_level", required=True),
                reason=_string(body, "reason", required=True),
                gap=_string(body, "gap", default=""),
                actor=_string(body, "actor", default="human"),
                evaluation_policy_revision=evaluation_policy_revision,
            )
            return JSONResponse(_json(get_candidate_workspace(session, candidate_id, evaluation_policy_revision=evaluation_policy_revision)))

    async def decide(request: Request) -> Response:
        body = await _body(request)
        candidate_id = request.path_params["candidate_id"]
        expected = _if_match_token(request)
        with v1_session_scope(factory) as session:
            if expected is not None:
                current = get_current_decision_context(
                    session, candidate_id, evaluation_policy_revision=evaluation_policy_revision
                ).hash
                _enforce_if_match(expected, current)
            make_human_decision(
                session,
                candidate_id,
                decision=_string(body, "decision", required=True),
                reason=_string(body, "reason", required=True),
                actor=_string(body, "actor", default="human"),
                evaluation_policy_revision=evaluation_policy_revision,
            )
            return JSONResponse(_json(get_candidate_workspace(session, candidate_id, evaluation_policy_revision=evaluation_policy_revision)))

    routes = [
        Route("/health/live", health_live, methods=["GET"]),
        Route("/health/ready", health_ready, methods=["GET"]),
        Route("/api/v1/info", v1_info, methods=["GET"]),
        Route("/api/v1/runtime/live", runtime_live, methods=["GET"]),
        Route("/api/v1/runtime/ready", runtime_ready, methods=["GET"]),
        Route("/api/v1/runtime/info", runtime_info, methods=["GET"]),
        Route("/api/v1/runtime/capabilities", runtime_capabilities, methods=["GET"]),
        Route("/api/v1/runtime/shutdown", runtime_shutdown, methods=["POST"]),
        Route("/api/v1/workbench", workbench, methods=["GET"]),
        Route("/api/v1/projects", projects, methods=["GET"]),
        Route("/api/v1/projects", create_project, methods=["POST"]),
        Route("/api/v1/projects/{project_id:str}/protocol-drafts", fork_protocol_draft, methods=["POST"]),
        Route("/api/v1/settings", settings, methods=["GET"]),
        Route("/api/v1/settings/provider", update_provider_settings, methods=["PATCH"]),
        Route("/api/v1/settings/capabilities/{name:str}", update_capability_policy, methods=["PATCH"]),
        Route("/api/v1/projects/{project_id:str}/protocol-workspace", protocol_workspace, methods=["GET"]),
        Route("/api/v1/protocol-revisions/{revision_id:str}", update_protocol, methods=["PATCH"]),
        Route("/api/v1/protocol-revisions/{revision_id:str}/publish", publish_protocol, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/sources/text", add_text_candidate_source, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/evidence/extract", extract_candidate_evidence, methods=["POST"]),
        Route("/api/v1/sources/{source_id:str}/content", source_content, methods=["GET"]),
        Route("/api/v1/sources/{source_id:str}/file", source_file, methods=["GET"]),
        Route("/api/v1/sources/{source_id:str}/page/{page_number:int}", source_page_render, methods=["GET"]),
        Route("/api/v1/sources/{source_id:str}/scoring-view", source_scoring_view, methods=["GET"]),
        Route("/api/v1/claims/{claim_id:str}/grounding", claim_grounding, methods=["GET"]),
        Route("/api/v1/claims/{claim_id:str}/review", review_claim, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/workspace", candidate_workspace, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/assessment", candidate_assessment, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/verifications", verify, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/decision", decide, methods=["POST"]),
    ]
    if supervisor_service is not None:
        # ADR-0003 S1: the Supervisor process publishes the attach protocol.
        from srw.supervisor.runtime import supervisor_routes

        routes.extend(supervisor_routes())

    def error_response(exc: Exception, *, status_code: int, code: str) -> Response:
        return JSONResponse({"detail": str(exc), "error": {"code": code}}, status_code=status_code)

    async def not_found_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=404, code="not_found")

    async def invariant_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=409, code="invariant_conflict")

    async def validation_handler(_request: Request, exc: Exception) -> Response:
        return error_response(exc, status_code=422, code="invalid_request")

    async def revision_conflict_handler(_request: Request, exc: Exception) -> Response:
        # ADR-0003 S2: 412 means the If-Match precondition failed. Nothing was
        # written and no audit event was produced; the client must reload state.
        return error_response(exc, status_code=412, code="revision_conflict")

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
            V1RevisionConflict: revision_conflict_handler,
            ProviderNotReadyError: provider_not_ready_handler,
            ProviderFailureError: provider_failure_handler,
            ProviderOutputInvalidError: provider_output_handler,
        },
    )

    app.add_middleware(LocalBoundaryMiddleware)

    # ADR-0003 S1: when this process is the Supervisor, publish the attach
    # service on app.state so the protocol routes can reach it.
    app.state.supervisor_service = supervisor_service
    app.state.supervisor_mode = supervisor_service is not None
    # ADR-0003 T8: backup/restore mutex consulted by the boundary middleware.
    from srw.runtime.backup_guard import BackupGuard

    app.state.backup_guard = BackupGuard()
    # ADR-0003 S3: session enforcement is a phase-2 flag (off until the
    # frontend carries the session/CSRF headers).
    app.state.enforce_carrier_sessions = bool(enforce_carrier_sessions)
    if supervisor_service is not None and enforce_carrier_sessions:
        from srw.supervisor.sessions import CarrierSessionMiddleware

        app.add_middleware(CarrierSessionMiddleware, service=supervisor_service)

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
    from srw.api.decision_operations_http import install_decision_operations_http_routes
    install_decision_operations_http_routes(app, factory, data_dir=resolved_data_dir, evaluation_policy_revision=evaluation_policy_revision)
    from srw.api.intelligence_http import install_intelligence_http_routes
    install_intelligence_http_routes(app, factory, data_dir=resolved_data_dir, knowledge_dir=resolved_knowledge_dir)
    from srw.api.sourcing_import_http import install_sourcing_import_http_routes
    install_sourcing_import_http_routes(app, factory)
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
