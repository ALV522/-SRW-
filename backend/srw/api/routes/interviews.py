"""Interview/event HTTP routes extracted from the full-workbench aggregate.

The module preserves the frozen transport contract while reusing authoritative
Candidate material, evidence, scorecard and audit services. It does not own a
second interview or evidence state machine (ADR-0002).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.commands import add_source, publish_source_into_current_material
from srw.modules.candidate.models import Candidate, Source
from srw.modules.fullworkbench import RecruitmentEvent
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.recruiting.workbench import scorecards_view, submit_scorecard
from srw.runtime.db.session import v1_session_scope


def _parse_iso(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V1InvariantError("scheduled_at must be ISO-8601") from exc


def _event_metadata(session, candidate_id: str, event_type: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise V1InvariantError("metadata must be an object")
    metadata = dict(value)
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    project = session.get(Project, candidate.project_id)
    known: set[str] = set()
    if project and project.current_protocol_revision_id:
        payload = ProtocolRepository(session).get_payload(project.current_protocol_revision_id)
        known = {str(item.get("criterion_key") or "") for item in (payload.get("criteria") or []) if isinstance(item, dict)}
    questions = metadata.get("questions", [])
    if questions is None:
        questions = []
    if not isinstance(questions, list) or any(not isinstance(item, dict) for item in questions):
        raise V1InvariantError("metadata.questions must be an array of objects")
    normalized_questions = []
    for item in questions:
        key = str(item.get("criterion_key") or "").strip()
        question = str(item.get("question") or "").strip()
        purpose = str(item.get("purpose") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question:
            raise V1InvariantError("interview question is required")
        if key and known and key not in known:
            raise V1InvariantError(f"unknown criterion_key: {key}")
        normalized_questions.append({"criterion_key": key, "question": question, "purpose": purpose, "answer": answer})
    feedback = metadata.get("feedback", [])
    if feedback is None:
        feedback = []
    if not isinstance(feedback, list) or any(not isinstance(item, dict) for item in feedback):
        raise V1InvariantError("metadata.feedback must be an array of objects")
    ratings = {"strong", "acceptable", "concern", "unknown"}
    normalized_feedback = []
    for item in feedback:
        key = str(item.get("criterion_key") or "").strip()
        rating = str(item.get("rating") or "unknown").strip()
        if not key:
            raise V1InvariantError("feedback criterion_key is required")
        if known and key not in known:
            raise V1InvariantError(f"unknown criterion_key: {key}")
        if rating not in ratings:
            raise V1InvariantError("feedback rating must be strong, acceptable, concern, or unknown")
        normalized_feedback.append({
            "criterion_key": key, "rating": rating,
            "observation": str(item.get("observation") or "").strip(),
            "supporting_evidence": str(item.get("supporting_evidence") or "").strip(),
            "counter_evidence": str(item.get("counter_evidence") or "").strip(),
            "recommendation": str(item.get("recommendation") or "").strip(),
        })
    metadata["questions"] = normalized_questions
    metadata["feedback"] = normalized_feedback
    metadata["overall_recommendation"] = str(metadata.get("overall_recommendation") or "").strip()
    return metadata


def _event_source_text(event: RecruitmentEvent, metadata: dict[str, Any]) -> str:
    lines = [f"Recruitment event: {event.event_type}", f"Title: {event.title}", f"Outcome: {event.outcome}"]
    if event.notes:
        lines += ["", "Notes:", event.notes]
    for index, question in enumerate(metadata.get("questions") or [], 1):
        lines += ["", f"Question {index}: {question.get('question', '')}", f"Criterion: {question.get('criterion_key', '')}", f"Purpose: {question.get('purpose', '')}", f"Answer: {question.get('answer', '')}"]
    for index, feedback in enumerate(metadata.get("feedback") or [], 1):
        lines += ["", f"Feedback {index} / {feedback.get('criterion_key', '')}", f"Rating: {feedback.get('rating', '')}", f"Observation: {feedback.get('observation', '')}", f"Supporting evidence: {feedback.get('supporting_evidence', '')}", f"Counter evidence: {feedback.get('counter_evidence', '')}", f"Recommendation: {feedback.get('recommendation', '')}"]
    if metadata.get("overall_recommendation"):
        lines += ["", f"Overall recommendation: {metadata['overall_recommendation']}"]
    return "\n".join(lines).strip()


def interview_routes(*, factory) -> list[Route]:
    async def events(request: Request) -> JSONResponse:
        candidate_id = request.path_params["candidate_id"]
        with factory() as session:
            rows = session.scalars(select(RecruitmentEvent).where(RecruitmentEvent.candidate_id == candidate_id).order_by(func.coalesce(RecruitmentEvent.scheduled_at, RecruitmentEvent.created_at).desc())).all()
            linked_ids = {row.source_id for row in rows if row.source_id}
            linked_sources = {row.id: row for row in session.scalars(select(Source).where(Source.id.in_(linked_ids))).all()} if linked_ids else {}
            def editable_event_evidence(row: RecruitmentEvent) -> bool:
                source = linked_sources.get(row.source_id)
                if source is None or source.candidate_id != candidate_id or row.event_state != "completed":
                    return False
                try:
                    metadata = json.loads(source.metadata_json or "{}")
                except (ValueError, TypeError):
                    return False
                return metadata.get("structured") is True and metadata.get("event_id") == row.id
            return JSONResponse({"events": [{
                "event_id": row.id, "event_type": row.event_type, "title": row.title, "notes": row.notes, "source_id": row.source_id,
                "editable_evidence_source": editable_event_evidence(row), "metadata": json.loads(row.metadata_json or "{}"),
                "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None, "duration_minutes": row.duration_minutes,
                "interviewer": row.interviewer, "location": row.location, "event_state": row.event_state, "outcome": row.outcome,
                "created_at": row.created_at.isoformat()} for row in rows]})

    async def add_event(request: Request) -> JSONResponse:
        candidate_id = request.path_params["candidate_id"]; body = await json_body(request); event_type = s_field(body, "event_type", required=True)
        if event_type not in {"phone_screen", "interview", "feedback", "note"}:
            raise V1InvariantError("unsupported event_type")
        state = s_field(body, "event_state", default="completed" if not body.get("scheduled_at") else "scheduled")
        if state not in {"scheduled", "completed", "cancelled", "no_show"}:
            raise V1InvariantError("unsupported event_state")
        try:
            duration = max(0, int(body.get("duration_minutes") or 0))
        except (TypeError, ValueError) as exc:
            raise V1InvariantError("duration_minutes must be an integer") from exc
        with v1_session_scope(factory) as session:
            candidate = session.get(Candidate, candidate_id)
            if not candidate:
                raise V1NotFoundError(f"candidate not found: {candidate_id}")
            source_id = s_field(body, "source_id") or None
            if source_id:
                source = session.get(Source, source_id)
                if not source:
                    raise V1NotFoundError(f"source not found: {source_id}")
                if source.candidate_id != candidate_id:
                    raise V1InvariantError("source belongs to another candidate")
            metadata = _event_metadata(session, candidate_id, event_type, body.get("metadata", {}))
            row = RecruitmentEvent(candidate_id=candidate_id,event_type=event_type,title=s_field(body,"title"),notes=s_field(body,"notes"),source_id=source_id,metadata_json=json.dumps(metadata,ensure_ascii=False,separators=(",",":")),scheduled_at=_parse_iso(s_field(body,"scheduled_at")),duration_minutes=duration,interviewer=s_field(body,"interviewer"),location=s_field(body,"location"),event_state=state,outcome=s_field(body,"outcome"))
            session.add(row); session.flush()
            if state == "completed" and event_type in {"phone_screen","interview","feedback"} and (metadata.get("questions") or metadata.get("feedback")) and not row.source_id:
                text = _event_source_text(row, metadata)
                source = add_source(session,candidate_id,source_kind=f"{event_type}_record",content_hash=content_hash({"event_id":row.id,"text":text}),text_content=text,media_type="text/plain",metadata={"event_id":row.id,"event_type":event_type,"structured":True})
                publish_source_into_current_material(session,candidate_id,source.id); row.source_id=source.id
            append_audit_event(session,event_type="RECRUITMENT_EVENT_CREATED",entity_type="recruitment_event",entity_id=row.id,actor=s_field(body,"actor",default="human"),payload={"event_type":event_type,"event_state":state,"source_id":row.source_id},project_id=candidate.project_id,candidate_id=candidate_id)
            return JSONResponse({"event_id":row.id,"event_state":row.event_state,"source_id":row.source_id})

    async def update_event(request: Request) -> JSONResponse:
        event_id=request.path_params["event_id"]; body=await json_body(request)
        with v1_session_scope(factory) as session:
            row=session.get(RecruitmentEvent,event_id)
            if not row: raise V1NotFoundError(f"event not found: {event_id}")
            candidate=session.get(Candidate,row.candidate_id); metadata=json.loads(row.metadata_json or "{}")
            if "metadata" in body:
                metadata=_event_metadata(session,row.candidate_id,row.event_type,body.get("metadata")); row.metadata_json=json.dumps(metadata,ensure_ascii=False,separators=(",",":"))
            if "event_state" in body:
                state=s_field(body,"event_state",required=True)
                if state not in {"scheduled","completed","cancelled","no_show"}: raise V1InvariantError("unsupported event_state")
                row.event_state=state
            if "outcome" in body: row.outcome=s_field(body,"outcome")
            if "notes" in body: row.notes=s_field(body,"notes")
            if "scheduled_at" in body: row.scheduled_at=_parse_iso(s_field(body,"scheduled_at"))
            if "duration_minutes" in body:
                try: row.duration_minutes=max(0,int(body.get("duration_minutes") or 0))
                except (TypeError,ValueError) as exc: raise V1InvariantError("duration_minutes must be an integer") from exc
            if "interviewer" in body: row.interviewer=s_field(body,"interviewer")
            if "location" in body: row.location=s_field(body,"location")
            if row.event_state=="completed" and row.event_type in {"phone_screen","interview","feedback"}:
                current_source=session.get(Source,row.source_id) if row.source_id else None
                source_meta=json.loads(current_source.metadata_json or "{}") if current_source else {}
                generated_here=(current_source is not None and source_meta.get("structured") is True and source_meta.get("event_id")==row.id and current_source.candidate_id==row.candidate_id)
                structured=bool(metadata.get("questions") or metadata.get("feedback"))
                if (not row.source_id and structured) or generated_here:
                    text=_event_source_text(row,metadata)
                    if current_source is None or current_source.text_content!=text:
                        origin=current_source.id if generated_here else None
                        provenance={"event_id":row.id,"event_type":row.event_type,"structured":True}
                        if origin: provenance["supersedes_source_id"]=origin
                        source=add_source(session,row.candidate_id,source_kind=f"{row.event_type}_record",content_hash=content_hash({"event_id":row.id,"text":text}),text_content=text,media_type="text/plain",metadata=provenance)
                        publish_source_into_current_material(session,row.candidate_id,source.id,supersedes_source_id=origin); row.source_id=source.id
            append_audit_event(session,event_type="RECRUITMENT_EVENT_UPDATED",entity_type="recruitment_event",entity_id=row.id,actor=s_field(body,"actor",default="human"),payload={"event_state":row.event_state,"outcome":row.outcome,"source_id":row.source_id},project_id=candidate.project_id if candidate else None,candidate_id=row.candidate_id)
            return JSONResponse({"event_id":row.id,"event_state":row.event_state,"outcome":row.outcome,"source_id":row.source_id,"metadata":metadata})

    async def event_scorecards(request: Request) -> JSONResponse:
        event_id=request.path_params["event_id"]
        if request.method=="GET":
            with factory() as session: return JSONResponse(scorecards_view(session,event_id))
        body=await json_body(request)
        with v1_session_scope(factory) as session:
            row=submit_scorecard(session,event_id,body)
            return JSONResponse({"scorecard_id":row.id,"event_id":row.event_id,"evaluator":row.evaluator,"state":row.state,"recommendation":row.recommendation})

    return [
        Route("/api/v1/candidates/{candidate_id:str}/events",events,methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/events",add_event,methods=["POST"]),
        Route("/api/v1/events/{event_id:str}",update_event,methods=["PATCH"]),
        Route("/api/v1/events/{event_id:str}/scorecards",event_scorecards,methods=["GET","POST"]),
    ]
