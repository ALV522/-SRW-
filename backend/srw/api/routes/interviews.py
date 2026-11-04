"""Interview and event routes extracted from the fullworkbench aggregate.

Behaviour is intentionally identical to the code that lived inside
``install_full_workbench_routes``: same paths, methods, response bodies, error
paths and transaction boundaries. The event metadata normalisation, structured
interview Source revisioning and scorecard submission stay where they were, in
``srw.recruiting.*`` and the Core session scope; this module only adapts HTTP.

Evidence note: editing a completed structured interview publishes a new Source
and MaterialRevision that supersedes the old one (Issue #41 / PR #57). That rule
is preserved verbatim, including the ``supersedes_source_id`` provenance marker.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.api.shared import publish_current_revision
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.commands import add_source
from srw.modules.candidate.models import Candidate, Source
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.recruiting.workbench import scorecards_view, submit_scorecard, require_pinned_event_revision
from srw.runtime.db.session import v1_session_scope

EVENT_STATES = {"scheduled", "completed", "cancelled", "no_show"}
SOURCE_BEARING_EVENT_TYPES = {"phone_screen", "interview", "feedback"}


def parse_iso(value: str):
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V1InvariantError("scheduled_at must be ISO-8601") from exc


def event_metadata(session, candidate_id: str, event_type: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise V1InvariantError("metadata must be an object")
    metadata = dict(value)
    if "protocol_revision_id" in metadata:
        pinned = metadata["protocol_revision_id"]
        if not isinstance(pinned, str) or not pinned.strip():
            raise V1InvariantError("protocol_revision_id must be a non-empty published revision")
        require_pinned_event_revision(session, candidate_id, pinned)
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    project = session.get(Project, candidate.project_id)
    known = set()
    if project and project.current_protocol_revision_id:
        payload = ProtocolRepository(session).get_payload(project.current_protocol_revision_id)
        known = {str(x.get("criterion_key") or "") for x in (payload.get("criteria") or []) if isinstance(x, dict)}
    questions = metadata.get("questions", [])
    if questions is None:
        questions = []
    if not isinstance(questions, list) or any(not isinstance(x, dict) for x in questions):
        raise V1InvariantError("metadata.questions must be an array of objects")
    normalized_q = []
    for item in questions:
        key = str(item.get("criterion_key") or "").strip()
        question = str(item.get("question") or "").strip()
        purpose = str(item.get("purpose") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question:
            raise V1InvariantError("interview question is required")
        if key and known and key not in known:
            raise V1InvariantError(f"unknown criterion_key: {key}")
        normalized_q.append({"criterion_key": key, "question": question, "purpose": purpose, "answer": answer})
    feedback = metadata.get("feedback", [])
    if feedback is None:
        feedback = []
    if not isinstance(feedback, list) or any(not isinstance(x, dict) for x in feedback):
        raise V1InvariantError("metadata.feedback must be an array of objects")
    ratings = {"strong", "acceptable", "concern", "unknown"}
    normalized_f = []
    for item in feedback:
        key = str(item.get("criterion_key") or "").strip()
        rating = str(item.get("rating") or "unknown").strip()
        if not key:
            raise V1InvariantError("feedback criterion_key is required")
        if known and key not in known:
            raise V1InvariantError(f"unknown criterion_key: {key}")
        if rating not in ratings:
            raise V1InvariantError("feedback rating must be strong, acceptable, concern, or unknown")
        normalized_f.append({
            "criterion_key": key,
            "rating": rating,
            "observation": str(item.get("observation") or "").strip(),
            "supporting_evidence": str(item.get("supporting_evidence") or "").strip(),
            "counter_evidence": str(item.get("counter_evidence") or "").strip(),
            "recommendation": str(item.get("recommendation") or "").strip(),
        })
    # A published revision ID alone is insufficient to authorize arbitrary
    # criterion keys: only the published interview-stage keys can be pinned.
    if metadata.get("protocol_revision_id") and event_type == "interview":
        published = ProtocolRepository(session).get_payload(metadata["protocol_revision_id"])
        stage_keys = set()
        for stage in published.get("assessment_stages") or []:
            if isinstance(stage, dict) and (stage.get("stage_key") == "interview" or stage.get("name") == "面试"):
                stage_keys.update(str(k) for k in (stage.get("criteria") or []) if isinstance(k, str) and k)
        question_keys = {q["criterion_key"] for q in normalized_q}
        if not stage_keys or not question_keys or not question_keys.issubset(stage_keys):
            raise V1InvariantError("pinned interview must use published interview-stage criteria")
        if any(f["criterion_key"] not in question_keys for f in normalized_f):
            raise V1InvariantError("pinned interview feedback must use its original questions")
        # The browser's name/definition snapshot is presentation data, not a
        # source of authority. Check supplied values and persist canonical data.
        criteria_by_key = {
            str(c.get("criterion_key")): c for c in (published.get("criteria") or [])
            if isinstance(c, dict) and c.get("criterion_key")
        }
        if not question_keys.issubset(criteria_by_key):
            raise V1InvariantError("pinned interview references a missing published criterion")
        requested = metadata.get("criteria_snapshot")
        if requested is not None:
            if not isinstance(requested, list) or any(not isinstance(c, dict) for c in requested):
                raise V1InvariantError("criteria_snapshot must be a list")
            for item in requested:
                key = str(item.get("criterion_key") or "")
                canonical = criteria_by_key.get(key)
                if (key not in question_keys or canonical is None or
                        str(item.get("name") or "") != str(canonical.get("name") or "") or
                        str(item.get("definition") or "") != str(canonical.get("definition") or "")):
                    raise V1InvariantError("criteria_snapshot disagrees with the published revision")
        metadata["criteria_snapshot"] = [
            {"criterion_key": key, "name": str(criteria_by_key[key].get("name") or ""),
             "definition": str(criteria_by_key[key].get("definition") or "")}
            for key in dict.fromkeys(q["criterion_key"] for q in normalized_q)
        ]
    metadata["questions"] = normalized_q
    metadata["feedback"] = normalized_f
    metadata["overall_recommendation"] = str(metadata.get("overall_recommendation") or "").strip()
    return metadata


def event_source_text(event: RecruitmentEvent, metadata: dict[str, Any]) -> str:
    lines = [f"Recruitment event: {event.event_type}", f"Title: {event.title}", f"Outcome: {event.outcome}"]
    if event.notes:
        lines += ["", "Notes:", event.notes]
    for idx, q in enumerate(metadata.get("questions") or [], 1):
        lines += ["", f"Question {idx}: {q.get('question', '')}", f"Criterion: {q.get('criterion_key', '')}",
                  f"Purpose: {q.get('purpose', '')}", f"Answer: {q.get('answer', '')}"]
    for idx, f in enumerate(metadata.get("feedback") or [], 1):
        lines += ["", f"Feedback {idx} / {f.get('criterion_key', '')}", f"Rating: {f.get('rating', '')}",
                  f"Observation: {f.get('observation', '')}", f"Supporting evidence: {f.get('supporting_evidence', '')}",
                  f"Counter evidence: {f.get('counter_evidence', '')}", f"Recommendation: {f.get('recommendation', '')}"]
    if metadata.get("overall_recommendation"):
        lines += ["", f"Overall recommendation: {metadata['overall_recommendation']}"]
    return "\n".join(lines).strip()


def interview_routes(*, factory) -> list[Route]:
    """Bind the interview/event endpoints to one Core session factory."""

    async def events(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        with factory() as session:
            rows = session.scalars(
                select(RecruitmentEvent)
                .where(RecruitmentEvent.candidate_id == cid)
                .order_by(func.coalesce(RecruitmentEvent.scheduled_at, RecruitmentEvent.created_at).desc())
            ).all()
            linked_ids = {x.source_id for x in rows if x.source_id}
            linked_sources = ({x.id: x for x in session.scalars(select(Source).where(Source.id.in_(linked_ids))).all()}
                              if linked_ids else {})

            def editable_event_evidence(x):
                source = linked_sources.get(x.source_id)
                if source is None or source.candidate_id != cid or x.event_state != "completed":
                    return False
                try:
                    metadata = json.loads(source.metadata_json or "{}")
                except (ValueError, TypeError):
                    return False
                return metadata.get("structured") is True and metadata.get("event_id") == x.id

            return JSONResponse({"events": [{
                "event_id": x.id, "event_type": x.event_type, "title": x.title, "notes": x.notes,
                "source_id": x.source_id, "editable_evidence_source": editable_event_evidence(x),
                "metadata": json.loads(x.metadata_json or "{}"),
                "scheduled_at": x.scheduled_at.isoformat() if x.scheduled_at else None,
                "duration_minutes": x.duration_minutes, "interviewer": x.interviewer, "location": x.location,
                "event_state": x.event_state, "outcome": x.outcome, "created_at": x.created_at.isoformat(),
            } for x in rows]})

    async def add_event(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        body = await json_body(request)
        event_type = s_field(body, "event_type", required=True)
        if event_type not in {"phone_screen", "interview", "feedback", "note"}:
            raise V1InvariantError("unsupported event_type")
        state = s_field(body, "event_state",
                        default="completed" if not body.get("scheduled_at") else "scheduled")
        if state not in EVENT_STATES:
            raise V1InvariantError("unsupported event_state")
        try:
            duration = max(0, int(body.get("duration_minutes") or 0))
        except (TypeError, ValueError) as exc:
            raise V1InvariantError("duration_minutes must be an integer") from exc
        with v1_session_scope(factory) as session:
            candidate = session.get(Candidate, cid)
            if not candidate:
                raise V1NotFoundError(f"candidate not found: {cid}")
            source_id = s_field(body, "source_id") or None
            if source_id:
                source = session.get(Source, source_id)
                if not source:
                    raise V1NotFoundError(f"source not found: {source_id}")
                if source.candidate_id != cid:
                    raise V1InvariantError("source belongs to another candidate")
            metadata = event_metadata(session, cid, event_type, body.get("metadata", {}))
            row = RecruitmentEvent(
                candidate_id=cid, event_type=event_type, title=s_field(body, "title"),
                notes=s_field(body, "notes"), source_id=source_id,
                metadata_json=json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                scheduled_at=parse_iso(s_field(body, "scheduled_at")), duration_minutes=duration,
                interviewer=s_field(body, "interviewer"), location=s_field(body, "location"),
                event_state=state, outcome=s_field(body, "outcome"),
            )
            session.add(row)
            session.flush()
            if (state == "completed" and event_type in SOURCE_BEARING_EVENT_TYPES
                    and (metadata.get("questions") or metadata.get("feedback")) and not row.source_id):
                text = event_source_text(row, metadata)
                source = add_source(
                    session, cid, source_kind=f"{event_type}_record",
                    content_hash=content_hash({"event_id": row.id, "text": text}),
                    text_content=text, media_type="text/plain",
                    metadata={"event_id": row.id, "event_type": event_type, "structured": True},
                )
                publish_current_revision(session, cid, source.id)
                row.source_id = source.id
            append_audit_event(
                session, event_type="RECRUITMENT_EVENT_CREATED", entity_type="recruitment_event",
                entity_id=row.id, actor=s_field(body, "actor", default="human"),
                payload={"event_type": event_type, "event_state": state, "source_id": row.source_id},
                project_id=candidate.project_id, candidate_id=cid,
            )
            return JSONResponse({"event_id": row.id, "event_state": row.event_state, "source_id": row.source_id})

    async def update_event(request: Request) -> JSONResponse:
        eid = request.path_params["event_id"]
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = session.get(RecruitmentEvent, eid)
            if not row:
                raise V1NotFoundError(f"event not found: {eid}")
            candidate = session.get(Candidate, row.candidate_id)
            metadata = json.loads(row.metadata_json or "{}")
            pinned = str(metadata.get("protocol_revision_id") or "").strip()
            # Administrative cancellation/no-show of a still-scheduled
            # historical event is NOT a structured assessment write. Keep the
            # legitimate recruiter action after protocol R1 -> R2, but only
            # permit a tightly bounded state/notes change with no metadata,
            # outcome, schedule, Source, or criteria replacement.
            safe_cancel = (
                row.event_state == "scheduled"
                and body.get("event_state") in {"cancelled", "no_show"}
                and set(body).issubset({"event_state", "notes", "actor"})
            )
            if pinned and not safe_cancel:
                # The event's own revision, not the browser's latest key list,
                # is authoritative for subsequent structured writes.
                require_pinned_event_revision(session, row.candidate_id, pinned)
            if "metadata" in body:
                updated = event_metadata(session, row.candidate_id, row.event_type, body.get("metadata"))
                if not pinned and updated.get("protocol_revision_id"):
                    # A legacy event has no authoritative creation-time revision.
                    # Never let a later PATCH assign it a revision it never used.
                    raise V1InvariantError("legacy event protocol revision cannot be introduced retroactively")
                if pinned and updated.get("protocol_revision_id") != pinned:
                    raise V1InvariantError("event protocol revision cannot be removed or replaced")
                metadata = updated
                row.metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
            if "event_state" in body:
                state = s_field(body, "event_state", required=True)
                if state not in EVENT_STATES:
                    raise V1InvariantError("unsupported event_state")
                row.event_state = state
            if "outcome" in body:
                row.outcome = s_field(body, "outcome")
            if "notes" in body:
                row.notes = s_field(body, "notes")
            if "scheduled_at" in body:
                row.scheduled_at = parse_iso(s_field(body, "scheduled_at"))
            if "duration_minutes" in body:
                try:
                    row.duration_minutes = max(0, int(body.get("duration_minutes") or 0))
                except (TypeError, ValueError) as exc:
                    raise V1InvariantError("duration_minutes must be an integer") from exc
            if "interviewer" in body:
                row.interviewer = s_field(body, "interviewer")
            if "location" in body:
                row.location = s_field(body, "location")
            if row.event_state == "completed" and row.event_type in SOURCE_BEARING_EVENT_TYPES:
                # An auto-published structured record is immutable evidence. Editing a
                # completed interview must publish a new Source/MaterialRevision rather
                # than leaving its event UI and the cited Source in disagreement.
                current_source = session.get(Source, row.source_id) if row.source_id else None
                source_meta = json.loads(current_source.metadata_json or "{}") if current_source else {}
                generated_here = (current_source is not None and source_meta.get("structured") is True
                                  and source_meta.get("event_id") == row.id
                                  and current_source.candidate_id == row.candidate_id)
                structured = bool(metadata.get("questions") or metadata.get("feedback"))
                if (not row.source_id and structured) or generated_here:
                    text = event_source_text(row, metadata)
                    if current_source is None or current_source.text_content != text:
                        origin = current_source.id if generated_here else None
                        provenance = {"event_id": row.id, "event_type": row.event_type, "structured": True}
                        if origin:
                            provenance["supersedes_source_id"] = origin
                        source = add_source(
                            session, row.candidate_id, source_kind=f"{row.event_type}_record",
                            content_hash=content_hash({"event_id": row.id, "text": text}),
                            text_content=text, media_type="text/plain", metadata=provenance,
                        )
                        publish_current_revision(session, row.candidate_id, source.id, supersedes_source_id=origin)
                        row.source_id = source.id
            append_audit_event(
                session, event_type="RECRUITMENT_EVENT_UPDATED", entity_type="recruitment_event",
                entity_id=row.id, actor=s_field(body, "actor", default="human"),
                payload={"event_state": row.event_state, "outcome": row.outcome, "source_id": row.source_id},
                project_id=candidate.project_id if candidate else None, candidate_id=row.candidate_id,
            )
            return JSONResponse({"event_id": row.id, "event_state": row.event_state,
                                 "outcome": row.outcome, "source_id": row.source_id, "metadata": metadata})

    async def event_scorecards(request: Request) -> JSONResponse:
        eid = request.path_params["event_id"]
        if request.method == "GET":
            with factory() as session:
                return JSONResponse(scorecards_view(session, eid))
        body = await json_body(request)
        with v1_session_scope(factory) as session:
            row = submit_scorecard(session, eid, body)
            return JSONResponse({"scorecard_id": row.id, "event_id": row.event_id, "evaluator": row.evaluator,
                                 "state": row.state, "recommendation": row.recommendation})

    async def candidate_event_scorecards(request: Request) -> JSONResponse:
        """Read an event only within its server-verified project/candidate context.

        This is an ownership consistency check, not multi-user authorization:
        local Host/session authentication remains a separate #43 contract.
        """
        pid = request.path_params["project_id"]
        cid = request.path_params["candidate_id"]
        eid = request.path_params["event_id"]
        with factory() as session:
            candidate = session.get(Candidate, cid)
            if candidate is None or candidate.project_id != pid:
                raise V1NotFoundError("scorecards not found in candidate context")
            event = session.get(RecruitmentEvent, eid)
            if event is None or event.candidate_id != cid:
                raise V1NotFoundError("scorecards not found in candidate context")
            return JSONResponse(scorecards_view(session, eid))

    return [
        Route("/api/v1/projects/{project_id:str}/candidates/{candidate_id:str}/events/{event_id:str}/scorecards",
              candidate_event_scorecards, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/events", events, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/events", add_event, methods=["POST"]),
        Route("/api/v1/events/{event_id:str}", update_event, methods=["PATCH"]),
        Route("/api/v1/events/{event_id:str}/scorecards", event_scorecards, methods=["GET", "POST"]),
    ]
