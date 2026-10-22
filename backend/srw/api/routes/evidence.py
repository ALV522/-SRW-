"""Evidence and source routes (ADR-0002 R2, tenth slice).

Eight routes over the evidence chain: text Source intake, synchronous evidence
extraction, Source content/file/page/scoring projections, Claim grounding and
Claim review.

Behaviour is identical to the code that lived inside ``create_v1_app``. The
handlers are copied verbatim; only three names are rebound locally:

* ``_body``/``_string``/``_bool`` → :mod:`srw.api.request_fields` (422 envelope),
* ``resolved_data_dir`` → the ``data_dir`` parameter.

Privacy contract preserved: extraction and the scoring view go through
``build_source_privacy_projection`` before any provider call or response, and
PDF page rendering only serves bytes for a validated blob hash from the local
store. Nothing here weakens that.

Scope note: the async variant ``/evidence/extract-task`` stays in
``fullworkbench`` because it enqueues background work through the Job Engine.
"""
from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from srw.api.serialization import jsonable as _json
from srw.api.request_fields import (
    body_boolean as _bool,
    body_dict as _body,
    body_string as _string,
)
from srw.evidence.grounding import enrich_source_locator
from srw.evidence.pipeline import extract_source_claims, persist_source_claims
from srw.intake.service import CandidateIntakeService
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.ai_runs.service import fail_ai_run, finish_ai_run, start_ai_run
from srw.modules.candidate.commands import confirm_claim
from srw.modules.candidate.models import Candidate, Claim, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.privacy.service import build_source_privacy_projection, rebind_privacy_safe_proposals
from srw.providers.contracts import ProviderOutputInvalidError
from srw.providers.runtime import ProviderRuntime
from srw.runtime.db.session import v1_session_scope
from srw.runtime.settings import RuntimeSettingsRepository


def evidence_routes(*, factory, registry, secrets, data_dir: Path) -> list[Route]:
    """Bind the evidence endpoints to one Core session factory and workspace."""

    resolved_data_dir = data_dir  # kept verbatim for the extracted handlers

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

    return [
        Route("/api/v1/candidates/{candidate_id:str}/sources/text", add_text_candidate_source, methods=["POST"]),
        Route("/api/v1/candidates/{candidate_id:str}/evidence/extract", extract_candidate_evidence, methods=["POST"]),
        Route("/api/v1/sources/{source_id:str}/content", source_content, methods=["GET"]),
        Route("/api/v1/sources/{source_id:str}/file", source_file, methods=["GET"]),
        Route("/api/v1/sources/{source_id:str}/page/{page_number:int}", source_page_render, methods=["GET"]),
        Route("/api/v1/sources/{source_id:str}/scoring-view", source_scoring_view, methods=["GET"]),
        Route("/api/v1/claims/{claim_id:str}/grounding", claim_grounding, methods=["GET"]),
        Route("/api/v1/claims/{claim_id:str}/review", review_claim, methods=["POST"]),
    ]
