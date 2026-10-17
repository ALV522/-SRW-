from __future__ import annotations

import base64, io, json, mimetypes, wave, threading, time, uuid
from time import perf_counter
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, or_, case
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, PlainTextResponse
from starlette.routing import Route

from srw.evidence.pipeline import extract_source_claims, persist_source_claims
from srw.intake.service import CandidateIntakeService
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash, decision_context_hash
from srw.modules.audit.models import AuditEvent
from srw.modules.audit.repository import append_audit_event
from srw.modules.ai_runs.service import start_ai_run, finish_ai_run, fail_ai_run
from srw.modules.candidate.commands import add_source, create_candidate
from srw.modules.candidate.models import Candidate, CandidateContact, Claim, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.modules.decision.models import CriterionJudgment, HumanDecision
from srw.modules.identity.models import CandidateIdentityReview
from srw.modules.calibration.models import JudgmentReviewItem
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.assessment import get_candidate_assessment
from srw.modules.fullworkbench import BlobStore, KnowledgeService, RecruitmentEvent, ReevaluationDraft, EvaluationSnapshot, RoleTemplate, TaskRecord, create_backup, diagnostics
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.recruiting.models import CandidateStageTransition, OfferRecord
from srw.modules.recruiting.operations_models import CandidateActionPlan, InterviewScorecardSubmission
from srw.recruiting.workbench import (update_job_setup, suggest_job_setup, upsert_action_plan, action_plan_view, contact_queue, phone_script, submit_scorecard, scorecards_view)
from srw.recruiting.operations import (
    PIPELINE_STAGES, OFFER_STATES, bulk_change_candidate_stage, change_candidate_stage,
    change_offer_status, change_project_status, create_offer, offer_view, pipeline_history,
    project_funnel,
)
from srw.providers.contracts import ProviderFailureError, ProviderNotReadyError, ProviderOutputInvalidError
from srw.providers.runtime import ProviderRuntime
from srw.privacy.service import build_source_privacy_projection, rebind_privacy_safe_proposals
from srw.release import get_release_state
from srw.runtime.db.schema import V1_SCHEMA_REVISION
from srw.runtime.diagnostic_bundle import build_privacy_safe_diagnostic_bundle
from srw.runtime.db.session import v1_session_scope
from srw.runtime.jobs.engine import JobEngine
from srw.runtime.jobs.models import Job
from srw.runtime.settings import RuntimeSettingsRepository
from srw.surfaces.workbench import get_workbench


def _body_dict(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict): raise V1InvariantError("request body must be an object")
    return body

async def _json_body(request: Request) -> dict[str, Any]:
    try: return _body_dict(await request.json())
    except V1InvariantError: raise
    except Exception as exc: raise V1InvariantError("request body must be valid JSON") from exc

def _s(body: dict[str,Any], key: str, default: str="", required: bool=False) -> str:
    v=body.get(key,default)
    if not isinstance(v,str): raise V1InvariantError(f"{key} must be a string")
    v=v.strip()
    if required and not v: raise V1InvariantError(f"{key} is required")
    return v

def _decode_file(body: dict[str,Any]) -> tuple[bytes,str,str]:
    filename=_s(body,"filename",required=True)
    media=_s(body,"media_type",default=mimetypes.guess_type(filename)[0] or "application/octet-stream")
    data=body.get("base64")
    if not isinstance(data,str) or not data: raise V1InvariantError("base64 is required")
    try: raw=base64.b64decode(data,validate=True)
    except Exception as exc: raise V1InvariantError("base64 is invalid") from exc
    if not raw: raise V1InvariantError("file is empty")
    if len(raw)>20*1024*1024: raise V1InvariantError("file exceeds 20 MB limit")
    return raw,filename,media


def _profile_view(session, secrets) -> dict[str,Any]:
    repo=RuntimeSettingsRepository(session); profiles={}
    for name in ("text_ai","ocr","asr"):
        p=repo.get_provider_profile(name)
        profiles[name]={"name":name,"provider_type":p.provider_type,"model":p.model,"base_url":p.base_url,"reasoning_effort":p.reasoning_effort,
                        "api_key_configured":secrets.configured(f"provider_{name}_api_key" if name!="text_ai" else "provider_api_key")}
    return {"profiles":profiles,"secret_persistence":secrets.persistence}


def _httpx():
    try: import httpx
    except ImportError as exc: raise ProviderNotReadyError("httpx provider pack is unavailable") from exc
    return httpx


def _key_for(name:str)->str: return "provider_api_key" if name=="text_ai" else f"provider_{name}_api_key"


def _task_begin(task: TaskRecord) -> float:
    task.attempt_count = int(task.attempt_count or 0) + 1
    task.status = "running"
    task.started_at = utc_now()
    task.finished_at = None
    task.duration_ms = 0
    task.error_code = ""
    task.error_message = ""
    return perf_counter()


def _task_finish(task: TaskRecord, started: float, *, status: str, result: dict[str, Any] | None = None, error_code: str = "", error_message: str = "") -> None:
    task.status = status
    task.finished_at = utc_now()
    task.duration_ms = max(0, int((perf_counter() - started) * 1000))
    task.error_code = error_code
    task.error_message = error_message
    task.result_json = json.dumps(result or {}, ensure_ascii=False, separators=(",", ":"))


def _task_json(task: TaskRecord) -> dict[str, Any]:
    try:
        result = json.loads(task.result_json or "{}")
    except Exception:
        result = {}
    return {
        "task_id": task.id, "type": task.task_type, "status": task.status,
        "candidate_id": task.candidate_id, "source_id": task.source_id,
        "result_source_id": task.result_source_id,
        "progress_current": task.progress_current, "progress_total": task.progress_total,
        "attempt_count": task.attempt_count,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "duration_ms": task.duration_ms,
        "error_code": task.error_code, "error_message": task.error_message,
        "result": result,
        "created_at": task.created_at.isoformat(),
    }


def _probe(session,secrets,name:str) -> dict[str,Any]:
    repo=RuntimeSettingsRepository(session); p=repo.get_provider_profile(name); key=secrets.get(_key_for(name))
    if not key: raise ProviderNotReadyError(f"{name} API key is not configured")
    httpx=_httpx(); base=p.base_url.rstrip("/")
    try:
        with httpx.Client(timeout=30.0) as c:
            if name=="asr":
                b=io.BytesIO()
                with wave.open(b,"wb") as w: w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b"\x00\x00"*800)
                uri="data:audio/wav;base64,"+base64.b64encode(b.getvalue()).decode()
                r=c.post(f"{base}/chat/completions",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":p.model,"messages":[{"role":"user","content":[{"type":"input_audio","input_audio":{"data":uri}}]}],"stream":False,"asr_options":{"enable_itn":False}})
            elif name=="ocr":
                # 1x1 valid PNG: endpoint reachability/model authentication probe. Real OCR is tested with user material.
                png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
                uri="data:image/png;base64,"+base64.b64encode(png).decode()
                r=c.post(f"{base}/chat/completions",headers={"Authorization":f"Bearer {key}"},json={"model":p.model,"messages":[{"role":"user","content":[{"type":"text","text":"Respond with OK."},{"type":"image_url","image_url":{"url":uri}}]}],"max_tokens":8})
            else:
                r=c.post(f"{base}/chat/completions",headers={"Authorization":f"Bearer {key}"},json={"model":p.model,"messages":[{"role":"user","content":"Reply exactly OK"}],"max_tokens":8})
            r.raise_for_status()
        return {"ok":True,"profile":name,"model":p.model}
    except Exception as exc:
        raise ProviderFailureError(f"{name} capability probe failed: {exc}") from exc


def _ocr_bytes(session,secrets,raw:bytes,media_type:str) -> str:
    p=RuntimeSettingsRepository(session).get_provider_profile("ocr"); key=secrets.get(_key_for("ocr"))
    if not key: raise ProviderNotReadyError("OCR API key is not configured")
    uri=f"data:{media_type};base64,"+base64.b64encode(raw).decode()
    httpx=_httpx()
    try:
        with httpx.Client(timeout=90.0) as c:
            r=c.post(p.base_url.rstrip("/")+"/chat/completions",headers={"Authorization":f"Bearer {key}"},json={"model":p.model,"messages":[{"role":"user","content":[{"type":"text","text":"Extract all visible text faithfully. Return plain text only."},{"type":"image_url","image_url":{"url":uri}}]}]})
            r.raise_for_status(); body=r.json(); text=str(body["choices"][0]["message"]["content"]).strip()
            if not text: raise ValueError("empty OCR output")
            return text
    except ProviderNotReadyError: raise
    except Exception as exc: raise ProviderFailureError(f"OCR request failed: {exc}") from exc


def _asr_bytes(session,secrets,raw:bytes,filename:str,media_type:str) -> str:
    p=RuntimeSettingsRepository(session).get_provider_profile("asr"); key=secrets.get(_key_for("asr"))
    if not key: raise ProviderNotReadyError("ASR API key is not configured")
    if len(raw) > 10*1024*1024: raise ProviderOutputInvalidError("qwen3-asr-flash accepts at most 10 MB; use a long-audio/file-transcription profile")
    data_uri=f"data:{media_type or 'audio/wav'};base64,"+base64.b64encode(raw).decode()
    httpx=_httpx()
    try:
        with httpx.Client(timeout=180.0) as c:
            r=c.post(p.base_url.rstrip("/")+"/chat/completions",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={
                "model":p.model,
                "messages":[{"role":"user","content":[{"type":"input_audio","input_audio":{"data":data_uri}}]}],
                "stream":False,
                "asr_options":{"enable_itn":False},
            })
            r.raise_for_status(); body=r.json(); text=str(body["choices"][0]["message"]["content"] or "").strip()
            if not text: raise ValueError("empty ASR output")
            return text
    except ProviderNotReadyError: raise
    except ProviderOutputInvalidError: raise
    except Exception as exc: raise ProviderFailureError(f"ASR request failed: {exc}") from exc


def install_full_workbench_routes(app, factory, registry, secrets, *, data_dir: Path, knowledge_dir: Path, database_path: Path, frontend_dist: Path | None = None, evaluation_policy_revision: str) -> None:
    data_dir=Path(data_dir); knowledge_dir=Path(knowledge_dir); blobs=BlobStore(data_dir/"blobs"); knowledge=KnowledgeService(knowledge_dir)

    async def dashboard(_r):
        from datetime import datetime, timezone, timedelta
        with factory() as s:
            metrics={
                "projects":s.scalar(select(func.count(Project.id)).where(Project.status!="archived")) or 0,
                "candidates":s.scalar(select(func.count(Candidate.id)).where(Candidate.archived.is_(False))) or 0,
                "open_tasks":s.scalar(select(func.count(TaskRecord.id)).where(TaskRecord.status.in_(("queued","running","waiting_provider","failed")))) or 0,
                "unreviewed_claims":s.scalar(select(func.count(Claim.id)).where(Claim.confirmation_state=="unreviewed")) or 0,
            }
            req_rows=s.execute(select(Project.status,func.count(Project.id)).group_by(Project.status)).all()
            requisitions={str(status):int(count) for status,count in req_rows}
            stage_rows=s.execute(select(Candidate.pipeline_stage,func.count(Candidate.id)).where(Candidate.archived.is_(False)).group_by(Candidate.pipeline_stage)).all()
            candidates_by_stage={stage:0 for stage in PIPELINE_STAGES}
            for stage,count in stage_rows: candidates_by_stage[str(stage or "new")]=int(count)
            offer_rows=s.execute(select(OfferRecord.status,func.count(OfferRecord.id)).group_by(OfferRecord.status)).all()
            offers_by_status={stage:0 for stage in OFFER_STATES}
            for status,count in offer_rows: offers_by_status[str(status)]=int(count)
            now=datetime.now(timezone.utc); horizon=now+timedelta(days=14)
            upcoming=s.scalar(select(func.count(RecruitmentEvent.id)).where(RecruitmentEvent.event_state=="scheduled",RecruitmentEvent.scheduled_at.is_not(None),RecruitmentEvent.scheduled_at>=now,RecruitmentEvent.scheduled_at<=horizon)) or 0
            recent=[{"event_type":x.event_type,"entity_type":x.entity_type,"entity_id":x.entity_id,"actor":x.actor,"created_at":x.created_at.isoformat()} for x in s.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(12)).all()]
            overdue=s.scalar(select(func.count(CandidateActionPlan.id)).where(CandidateActionPlan.next_contact_at.is_not(None),CandidateActionPlan.next_contact_at<now,CandidateActionPlan.contact_status.in_(("to_contact","callback","attempted")))) or 0
            today_end=now+timedelta(days=1)
            today_contacts=s.scalar(select(func.count(CandidateActionPlan.id)).where(CandidateActionPlan.next_contact_at.is_not(None),CandidateActionPlan.next_contact_at>=now,CandidateActionPlan.next_contact_at<today_end,CandidateActionPlan.contact_status.in_(("to_contact","callback","attempted")))) or 0
            pending_scorecards=s.scalar(select(func.count(RecruitmentEvent.id)).where(RecruitmentEvent.event_state=="completed",RecruitmentEvent.event_type=="interview",~RecruitmentEvent.id.in_(select(InterviewScorecardSubmission.event_id).where(InterviewScorecardSubmission.state=="submitted")))) or 0
            stale_reevaluations=s.scalar(select(func.count(ReevaluationDraft.id)).where(ReevaluationDraft.state=="stale")) or 0
            pending_identity=s.scalar(select(func.count(CandidateIdentityReview.id)).where(CandidateIdentityReview.status=="pending")) or 0
            open_judgment_reviews=s.scalar(select(func.count(JudgmentReviewItem.id)).where(JudgmentReviewItem.state=="open")) or 0
            operational_items=[]
            contact_rows=s.execute(
                select(CandidateActionPlan,Candidate.display_name,Project.title)
                .join(Candidate,Candidate.id==CandidateActionPlan.candidate_id)
                .join(Project,Project.id==CandidateActionPlan.project_id)
                .where(
                    CandidateActionPlan.next_contact_at.is_not(None),
                    CandidateActionPlan.next_contact_at<now,
                    CandidateActionPlan.contact_status.in_(("to_contact","callback","attempted")),
                    Candidate.archived.is_(False),
                    Project.status!="archived",
                )
                .order_by(CandidateActionPlan.next_contact_at.asc(),CandidateActionPlan.id)
                .limit(6)
            ).all()
            for plan,candidate_name,project_title in contact_rows:
                operational_items.append({
                    "kind":"overdue_contact",
                    "project_id":plan.project_id,
                    "project_title":project_title,
                    "candidate_id":plan.candidate_id,
                    "candidate_name":candidate_name,
                    "event_id":"",
                    "title":"逾期联系",
                    "detail":plan.next_contact_at.isoformat() if plan.next_contact_at else "",
                })
            feedback_rows=s.execute(
                select(RecruitmentEvent,Candidate.display_name,Project.id,Project.title)
                .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
                .join(Project,Project.id==Candidate.project_id)
                .where(
                    RecruitmentEvent.event_state=="completed",
                    RecruitmentEvent.event_type=="interview",
                    ~RecruitmentEvent.id.in_(select(InterviewScorecardSubmission.event_id).where(InterviewScorecardSubmission.state=="submitted")),
                    Candidate.archived.is_(False),
                    Project.status!="archived",
                )
                .order_by(RecruitmentEvent.scheduled_at.asc(),RecruitmentEvent.created_at.asc(),RecruitmentEvent.id)
                .limit(6)
            ).all()
            for event,candidate_name,project_id,project_title in feedback_rows:
                operational_items.append({
                    "kind":"pending_interview_feedback",
                    "project_id":project_id,
                    "project_title":project_title,
                    "candidate_id":event.candidate_id,
                    "candidate_name":candidate_name,
                    "event_id":event.id,
                    "title":"待提交面试反馈",
                    "detail":event.title or "结构化面试",
                })
            workbench=get_workbench(s,evaluation_policy_revision=evaluation_policy_revision)
            return JSONResponse({
                "metrics":metrics,"recent":recent,"recent_activity":recent,
                "requisitions_by_status":requisitions,
                "candidates_by_stage":candidates_by_stage,
                "offers_by_status":offers_by_status,
                "upcoming_interviews":int(upcoming),
                "evidence_review_backlog":int(metrics["unreviewed_claims"]),
                "operational_todos":{"overdue_contacts":int(overdue),"today_contacts":int(today_contacts),"pending_interview_feedback":int(pending_scorecards),"stale_reevaluations":int(stale_reevaluations),"pending_identity_reviews":int(pending_identity),"open_judgment_reviews":int(open_judgment_reviews)},
                "operational_queue":{"items":operational_items[:12],"total":len(operational_items)},
                "decision_workbench":{
                    "conflict_count":workbench.conflict_count,
                    "verify_count":workbench.verify_count,
                    "ready_count":workbench.ready_count,
                    "items":[{
                        "work_item_id":x.work_item_id,
                        "project_id":x.project_id,
                        "project_title":x.project_title,
                        "candidate_id":x.candidate_id,
                        "candidate_name":x.candidate_name,
                        "criterion_name":x.criterion_name,
                        "action_type":x.action_type,
                        "reason":x.reason,
                    } for x in workbench.items[:12]],
                    "total":len(workbench.items),
                },
            })

    async def provider_settings(_r):
        with factory() as s: return JSONResponse(_profile_view(s,secrets))
    async def provider_update(r):
        name=r.path_params["name"]
        if name not in {"text_ai","ocr","asr"}: raise HTTPException(404)
        b=await _json_body(r)
        with v1_session_scope(factory) as s:
            current=RuntimeSettingsRepository(s).get_provider_profile(name)
            RuntimeSettingsRepository(s).update_provider_profile(name,provider_type=_s(b,"provider_type",current.provider_type),model=_s(b,"model",current.model),base_url=_s(b,"base_url",current.base_url),reasoning_effort=_s(b,"reasoning_effort",current.reasoning_effort))
            if "api_key" in b: secrets.set(_key_for(name),_s(b,"api_key"))
            return JSONResponse(_profile_view(s,secrets))
    async def provider_probe(r):
        name=r.path_params["name"]
        with factory() as s: return JSONResponse(_probe(s,secrets,name))

    def _evidence_result(result) -> dict[str, Any]:
        return {
            "source_id": result.source_id,
            "proposed": result.proposed,
            "created": result.created,
            "duplicate": result.duplicate,
            "rejected": result.rejected,
            "claim_ids": list(result.claim_ids),
        }

    def _queue_task_job(s, task: TaskRecord) -> Job:
        s.add(task); s.flush()
        job = JobEngine(s).enqueue(
            f"task.{task.task_type}", {"task_id": task.id},
            idempotency_key=f"task:{task.id}", priority=100, resource_class="io",
        )
        task.job_id = job.id
        return job

    async def extract_evidence_task(r):
        cid=r.path_params["candidate_id"]; body=await _json_body(r); source_id=_s(body,"source_id",required=True)
        with v1_session_scope(factory) as s:
            source=s.get(Source,source_id)
            if not source: raise V1NotFoundError(f"source not found: {source_id}")
            if source.candidate_id != cid: raise V1InvariantError("source belongs to another candidate")
            task=TaskRecord(task_type="evidence_extract",status="queued",candidate_id=cid,source_id=source_id,payload_json=json.dumps({"source_id":source_id},ensure_ascii=False))
            job=_queue_task_job(s,task)
            return JSONResponse({"task_id":task.id,"job_id":job.id,"task_status":"queued"})

    async def list_candidates(r):
        pid=r.path_params["project_id"]
        q=(r.query_params.get("q") or "").strip()[:200]
        archived=(r.query_params.get("archived") or "all").strip().lower()
        material=(r.query_params.get("material") or "all").strip().lower()
        stage=(r.query_params.get("stage") or "all").strip().lower()
        if archived not in {"all","active","archived"}: raise V1InvariantError("archived must be all, active, or archived")
        if material not in {"all","with","without"}: raise V1InvariantError("material must be all, with, or without")
        if stage != "all" and stage not in PIPELINE_STAGES: raise V1InvariantError("unsupported pipeline stage")
        try:
            limit=min(200,max(1,int(r.query_params.get("limit","100"))))
            offset=max(0,int(r.query_params.get("offset","0")))
        except ValueError as exc:
            raise V1InvariantError("limit and offset must be integers") from exc
        filters=[Candidate.project_id==pid]
        if q: filters.append(func.lower(Candidate.display_name).like(f"%{q.lower()}%"))
        if archived=="active": filters.append(Candidate.archived.is_(False))
        elif archived=="archived": filters.append(Candidate.archived.is_(True))
        if material=="with": filters.append(Candidate.current_material_revision_id.is_not(None))
        elif material=="without": filters.append(Candidate.current_material_revision_id.is_(None))
        if stage!="all": filters.append(Candidate.pipeline_stage==stage)
        with factory() as s:
            total=s.scalar(select(func.count(Candidate.id)).where(*filters)) or 0
            rows=s.scalars(select(Candidate).where(*filters).order_by(Candidate.archived,Candidate.created_at.desc(),Candidate.id).limit(limit).offset(offset)).all()
            return JSONResponse({"candidates":[{"candidate_id":x.id,"display_name":x.display_name,"archived":x.archived,"merged_into_candidate_id":x.merged_into_candidate_id,"pipeline_stage":x.pipeline_stage or "new","has_material":bool(x.current_material_revision_id),"created_at":x.created_at.isoformat()} for x in rows],"total":total,"limit":limit,"offset":offset})
    async def candidate_summary(r):
        cid=r.path_params["candidate_id"]
        with factory() as s:
            cand=s.get(Candidate,cid)
            if not cand: raise V1NotFoundError(f"candidate not found: {cid}")
            contact=s.scalar(select(CandidateContact).where(CandidateContact.candidate_id==cid))
            offer=s.scalar(select(OfferRecord).where(OfferRecord.candidate_id==cid).order_by(OfferRecord.created_at.desc()).limit(1))
            return JSONResponse({
                "candidate_id":cand.id,"project_id":cand.project_id,"display_name":cand.display_name,"pipeline_stage":cand.pipeline_stage or "new",
                "archived":bool(cand.archived),"merged_into_candidate_id":cand.merged_into_candidate_id,"has_material":bool(cand.current_material_revision_id),
                "contact":{"phone":contact.phone if contact else "","email":contact.email if contact else "","user_confirmed":bool(contact.user_confirmed) if contact else False},
                "offer_status":offer.status if offer else "",
            })

    async def candidate_search(r):
        pid=r.path_params["project_id"];q=(r.query_params.get("q") or "").strip()[:200]
        try: limit=min(50,max(1,int(r.query_params.get("limit","20"))))
        except ValueError as exc: raise V1InvariantError("limit must be an integer") from exc
        filters=[Candidate.project_id==pid,Candidate.archived.is_(False)]
        if q: filters.append(func.lower(Candidate.display_name).like(f"%{q.lower()}%"))
        with factory() as s:
            rows=s.scalars(select(Candidate).where(*filters).order_by(Candidate.display_name,Candidate.id).limit(limit)).all()
            return JSONResponse({"candidates":[{"candidate_id":x.id,"display_name":x.display_name,"pipeline_stage":x.pipeline_stage or "new","has_material":bool(x.current_material_revision_id)} for x in rows]})

    async def cockpit(r):
        pid=r.path_params["project_id"]
        try: limit=min(100,max(1,int(r.query_params.get("limit","25"))));offset=max(0,int(r.query_params.get("offset","0")))
        except ValueError as exc: raise V1InvariantError("limit and offset must be integers") from exc
        with factory() as s:
            if s.get(Project,pid) is None: raise V1NotFoundError(f"project not found: {pid}")
            total=s.scalar(select(func.count(Candidate.id)).where(Candidate.project_id==pid,Candidate.archived.is_(False))) or 0
            claim_counts=(select(Claim.candidate_id.label("cid"),func.sum(case((Claim.confirmation_state=="confirmed",1),else_=0)).label("confirmed"),func.sum(case((Claim.confirmation_state=="unreviewed",1),else_=0)).label("unreviewed")).group_by(Claim.candidate_id).subquery())
            judgment_counts=(select(CriterionJudgment.candidate_id.label("cid"),func.count(CriterionJudgment.id).label("judgments")).group_by(CriterionJudgment.candidate_id).subquery())
            rows=s.execute(select(Candidate,func.coalesce(claim_counts.c.confirmed,0),func.coalesce(claim_counts.c.unreviewed,0),func.coalesce(judgment_counts.c.judgments,0)).outerjoin(claim_counts,claim_counts.c.cid==Candidate.id).outerjoin(judgment_counts,judgment_counts.c.cid==Candidate.id).where(Candidate.project_id==pid,Candidate.archived.is_(False)).order_by(Candidate.created_at.desc(),Candidate.id).limit(limit).offset(offset)).all()
            output=[]
            for c,a,b,j in rows:
                assessment=None
                if c.current_material_revision_id:
                    try: assessment=get_candidate_assessment(s,c.id,evaluation_policy_revision=evaluation_policy_revision)
                    except Exception: assessment=None
                output.append({"candidate_id":c.id,"display_name":c.display_name,"pipeline_stage":c.pipeline_stage or "new","has_material":bool(c.current_material_revision_id),"confirmed_claims":int(a or 0),"unreviewed_claims":int(b or 0),"judgments":int(j or 0),"assessment":assessment})
            return JSONResponse({"candidates":output,"total":int(total),"limit":limit,"offset":offset})

    async def add_candidate(r):
        pid=r.path_params["project_id"]; b=await _json_body(r)
        with v1_session_scope(factory) as s:
            x=create_candidate(s,pid,_s(b,"display_name",required=True)); return JSONResponse({"candidate_id":x.id,"display_name":x.display_name})
    async def archive_candidate(r):
        cid=r.path_params["candidate_id"]
        with v1_session_scope(factory) as s:
            x=s.get(Candidate,cid)
            if not x: raise V1NotFoundError(f"candidate not found: {cid}")
            x.archived=True; return JSONResponse({"candidate_id":cid,"archived":True})
    async def restore_candidate(r):
        cid=r.path_params["candidate_id"]
        with v1_session_scope(factory) as s:
            x=s.get(Candidate,cid)
            if not x: raise V1NotFoundError(f"candidate not found: {cid}")
            if x.merged_into_candidate_id:
                raise V1InvariantError("merged source identity cannot be restored; open the canonical candidate instead")
            x.archived=False; return JSONResponse({"candidate_id":cid,"archived":False})

    async def archive_project(r):
        pid=r.path_params["project_id"]
        with v1_session_scope(factory) as s:
            x=change_project_status(s,pid,"archived",actor="human",reason="project archived")
            return JSONResponse({"project_id":pid,"status":x.status})
    async def restore_project(r):
        pid=r.path_params["project_id"]
        with v1_session_scope(factory) as s:
            x=s.get(Project,pid)
            if not x: raise V1NotFoundError(f"project not found: {pid}")
            target="open" if x.current_protocol_revision_id else "draft"
            x=change_project_status(s,pid,target,actor="human",reason="project restored")
            return JSONResponse({"project_id":pid,"status":x.status})

    def _publish_current(s,cid,new_source_id):
        cand=s.get(Candidate,cid); ids=[]
        if cand and cand.current_material_revision_id:
            try: ids=get_current_source_ids(s,cid)
            except Exception: ids=[]
        if new_source_id not in ids: ids.append(new_source_id)
        return MaterialRepository(s).publish_revision(cid,ids,{"action":"v1_intake","source_id":new_source_id})

    def _queue_media_task(s, *, task_type: str, candidate_id: str, source_id: str, payload: dict[str,Any]) -> TaskRecord:
        task=TaskRecord(task_type=task_type,status="queued",candidate_id=candidate_id,source_id=source_id,payload_json=json.dumps(payload,ensure_ascii=False,separators=(",",":")))
        _queue_task_job(s,task)
        return task

    def _ingest_candidate_file(s, cid: str, *, raw: bytes, filename: str, media: str, source_kind: str = "resume") -> dict[str, Any]:
        digest=blobs.put(raw)
        cand=s.get(Candidate,cid)
        if not cand: raise V1NotFoundError(f"candidate not found: {cid}")
        lower=filename.lower()
        if media.startswith(("audio/","video/")) or lower.endswith((".mp3",".wav",".m4a",".mp4",".webm",".aac",".flac")):
            original=add_source(s,cid,source_kind="asr_input",content_hash=digest,text_content="",media_type=media,blob_hash=digest,metadata={"filename":filename})
            task=_queue_media_task(s,task_type="asr",candidate_id=cid,source_id=original.id,payload={"blob_hash":digest,"filename":filename,"media_type":media})
            return {"source_id":original.id,"task_id":task.id,"job_id":task.job_id,"task_status":"queued","intake_status":"received","extraction_status":"queued"}
        if media.startswith("image/") or lower.endswith((".png",".jpg",".jpeg",".bmp",".webp",".tif",".tiff")):
            original=add_source(s,cid,source_kind="ocr_input",content_hash=digest,text_content="",media_type=media,blob_hash=digest,metadata={"filename":filename})
            task=_queue_media_task(s,task_type="ocr",candidate_id=cid,source_id=original.id,payload={"blob_hash":digest,"filename":filename,"media_type":media})
            return {"source_id":original.id,"task_id":task.id,"job_id":task.job_id,"task_status":"queued","intake_status":"received","extraction_status":"queued"}
        try:
            from srw.runtime.settings import CapabilityManager
            svc=CandidateIntakeService(s,capability_manager=CapabilityManager(s,registry))
            src=svc.import_document(cid,content=raw,filename=filename,media_type=media,source_kind=source_kind,blob_hash=digest)
            _publish_current(s,cid,src.id)
            extractor={}
            try: extractor=json.loads(src.metadata_json or "{}").get("extractor") or {}
            except Exception: extractor={}
            empty_pages=[int(x) for x in (extractor.get("empty_pages") or []) if isinstance(x,int) or (isinstance(x,str) and x.isdigit())]
            if lower.endswith(".pdf") and empty_pages:
                task=_queue_media_task(s,task_type="ocr_pdf",candidate_id=cid,source_id=src.id,payload={"blob_hash":digest,"filename":filename,"media_type":media,"empty_pages":empty_pages,"base_source_id":src.id})
                return {"source_id":src.id,"material_revision_id":s.get(Candidate,cid).current_material_revision_id,"task_id":task.id,"job_id":task.job_id,"task_status":"queued","intake_status":"published","extraction_status":"queued_partial_ocr","empty_pages":empty_pages}
            return {"source_id":src.id,"material_revision_id":s.get(Candidate,cid).current_material_revision_id,"intake_status":"published","extraction_status":"not_required"}
        except Exception as exc:
            if lower.endswith(".pdf"):
                original=add_source(s,cid,source_kind="ocr_input",content_hash=digest,text_content="",media_type=media,blob_hash=digest,metadata={"filename":filename,"fallback":"pdf_ocr"})
                task=_queue_media_task(s,task_type="ocr_pdf",candidate_id=cid,source_id=original.id,payload={"blob_hash":digest,"filename":filename,"media_type":media})
                return {"source_id":original.id,"task_id":task.id,"job_id":task.job_id,"task_status":"queued","intake_status":"received","extraction_status":"queued"}
            raise V1InvariantError(f"document intake failed: {exc}") from exc

    async def ingest_file(r):
        cid=r.path_params["candidate_id"]; b=await _json_body(r); raw,filename,media=_decode_file(b)
        with v1_session_scope(factory) as s:
            result=_ingest_candidate_file(s,cid,raw=raw,filename=filename,media=media,source_kind=_s(b,"source_kind","resume"))
            return JSONResponse(result)

    async def batch_intake(r):
        pid=r.path_params["project_id"]; body=await _json_body(r); items=body.get("items")
        if not isinstance(items,list) or not items: raise V1InvariantError("items must be a non-empty array")
        if len(items)>50: raise V1InvariantError("batch intake supports at most 50 files; split the batch explicitly")
        prepared=[]; raw_total=0
        for index,item in enumerate(items):
            if not isinstance(item,dict): raise V1InvariantError("batch item must be an object")
            raw,filename,media=_decode_file(item); raw_total += len(raw)
            if raw_total > 100*1024*1024: raise V1InvariantError("batch intake exceeds 100 MB aggregate limit")
            digest=blobs.put(raw)
            prepared.append({"index":index,"blob_hash":digest,"filename":filename,"media_type":media,"display_name":_s(item,"display_name") or Path(filename).stem.strip() or f"Candidate {index+1}","source_kind":_s(item,"source_kind","resume")})
        with v1_session_scope(factory) as s:
            if s.get(Project,pid) is None: raise V1NotFoundError(f"project not found: {pid}")
            task=TaskRecord(task_type="batch_candidate_intake",status="queued",progress_total=len(prepared),payload_json=json.dumps({"project_id":pid,"items":prepared},ensure_ascii=False,separators=(",",":")),result_json=json.dumps({"items":[]},ensure_ascii=False))
            job=_queue_task_job(s,task)
            return JSONResponse({"task_id":task.id,"job_id":job.id,"status":"queued","item_count":len(prepared)})

    def _job_owned(s, job_id: str, worker_id: str, token: str | None) -> bool:
        return JobEngine(s).is_owned(job_id,worker_id,token)

    def _recompute_batch_status(task: TaskRecord, ledger: list[dict[str, Any]]) -> None:
        statuses=[str(x.get("status") or "") for x in ledger]
        failed=sum(1 for x in statuses if x=="failed")
        pending=sum(1 for x in statuses if x in {"processing","waiting_provider","queued"})
        if pending:
            task.status="partial"
            task.error_code="downstream_pending"
            task.error_message=f"{pending} item(s) still require downstream processing"
        elif failed:
            task.status="failed" if failed==len(statuses) else "partial"
            task.error_code="batch_partial_failure"
            task.error_message=f"{failed} item(s) failed"
        else:
            task.status="succeeded"
            task.error_code=""
            task.error_message=""
        task.finished_at=utc_now()

    def _sync_parent_batch_item(s, child: TaskRecord, *, child_status: str) -> None:
        try:
            payload=json.loads(child.payload_json or "{}")
        except Exception:
            return
        parent_id=str(payload.get("parent_batch_task_id") or "")
        if not parent_id: return
        try: idx=int(payload.get("parent_batch_index"))
        except Exception: return
        parent=s.get(TaskRecord,parent_id)
        if parent is None: return
        current=json.loads(parent.result_json or "{}")
        ledger=[x for x in current.get("items",[]) if isinstance(x,dict)]
        for entry in ledger:
            if int(entry.get("index",-1))==idx:
                entry["status"] = "waiting_provider" if child_status=="waiting_provider" else ("ready_for_review" if child_status=="succeeded" else child_status)
                entry["extraction_status"] = child_status
                entry["child_task_id"] = child.id
                if child_status=="failed": entry["error"] = child.error_message
                break
        parent.result_json=json.dumps({"items":ledger},ensure_ascii=False,separators=(",",":"))
        _recompute_batch_status(parent,ledger)

    def _process_batch_job(job_id: str, worker_id: str, token: str, task_id: str) -> None:
        with factory() as s:
            task=s.get(TaskRecord,task_id)
            if not task: raise V1InvariantError(f"task not found: {task_id}")
            payload=json.loads(task.payload_json or "{}")
            items=list(payload.get("items") or []); pid=str(payload.get("project_id") or "")
        for item in items:
            idx=int(item.get("index",0))
            with factory() as s:
                task=s.get(TaskRecord,task_id); job=s.get(Job,job_id)
                if not task or not job or task.cancel_requested or job.status=="cancelled": return
                current=json.loads(task.result_json or "{}")
                existing={int(x.get("index",-1)):x for x in current.get("items",[]) if isinstance(x,dict)}
                if idx in existing and existing[idx].get("checkpoint_committed"):
                    continue
            raw=blobs.get(str(item.get("blob_hash") or ""))
            try:
                with v1_session_scope(factory) as s:
                    if not _job_owned(s,job_id,worker_id,token): return
                    task=s.get(TaskRecord,task_id)
                    if not task or task.cancel_requested: return
                    current=json.loads(task.result_json or "{}"); ledger=[x for x in current.get("items",[]) if isinstance(x,dict) and int(x.get("index",-1))!=idx]
                    cand=create_candidate(s,pid,str(item.get("display_name") or f"Candidate {idx+1}"))
                    intake=_ingest_candidate_file(s,cand.id,raw=raw,filename=str(item.get("filename") or "file"),media=str(item.get("media_type") or "application/octet-stream"),source_kind=str(item.get("source_kind") or "resume"))
                    child_task_id=str(intake.get("task_id") or "")
                    if child_task_id:
                        child=s.get(TaskRecord,child_task_id)
                        if child is not None:
                            cp=json.loads(child.payload_json or "{}")
                            cp["parent_batch_task_id"]=task_id; cp["parent_batch_index"]=idx
                            child.payload_json=json.dumps(cp,ensure_ascii=False,separators=(",",":"))
                    extraction=str(intake.get("extraction_status") or "not_required")
                    pending=extraction.startswith("queued")
                    entry={"index":idx,"status":"processing" if pending else "ready_for_review","candidate_id":cand.id,"display_name":cand.display_name,
                           "intake_status":str(intake.get("intake_status") or "received"),"extraction_status":extraction,"review_status":"pending",
                           "child_task_id":child_task_id or None,"intake":intake,"checkpoint_committed":True}
                    ledger.append(entry); ledger.sort(key=lambda x:int(x.get("index",0)))
                    task.result_json=json.dumps({"items":ledger},ensure_ascii=False,separators=(",",":"));task.progress_current=len(ledger)
            except Exception as exc:
                with v1_session_scope(factory) as s:
                    if not _job_owned(s,job_id,worker_id,token): return
                    task=s.get(TaskRecord,task_id)
                    current=json.loads(task.result_json or "{}"); ledger=[x for x in current.get("items",[]) if isinstance(x,dict) and int(x.get("index",-1))!=idx]
                    ledger.append({"index":idx,"status":"failed","error":str(exc),"checkpoint_committed":True});ledger.sort(key=lambda x:int(x.get("index",0)))
                    task.result_json=json.dumps({"items":ledger},ensure_ascii=False,separators=(",",":"));task.progress_current=len(ledger)
        with v1_session_scope(factory) as s:
            if not _job_owned(s,job_id,worker_id,token): return
            task=s.get(TaskRecord,task_id); ledger=json.loads(task.result_json or "{}").get("items",[])
            _recompute_batch_status(task,ledger)
            s.flush(); JobEngine(s).succeed(job_id,worker_id,token)

    def _process_single_job(job_id: str, worker_id: str, token: str, task_id: str) -> None:
        with factory() as s:
            task=s.get(TaskRecord,task_id)
            if not task: raise V1InvariantError(f"task not found: {task_id}")
            task_type=task.task_type; payload=json.loads(task.payload_json or "{}"); candidate_id=task.candidate_id; source_id=task.source_id
            if task.cancel_requested: return
        started=perf_counter()
        ai_run_id=None
        try:
            if task_type=="evidence_extract":
                requested_source_id=str(payload.get("source_id") or source_id or "")
                runtime=ProviderRuntime(registry=registry,secrets=secrets)
                # Persist the running transition in a short transaction, then release it.
                with v1_session_scope(factory) as s:
                    if not _job_owned(s,job_id,worker_id,token): return
                    task=s.get(TaskRecord,task_id)
                    if not task or task.cancel_requested: return
                    _task_begin(task)
                    retry_count=max(0,int(task.attempt_count or 0)-1)
                # Read immutable request/config state, close the DB session, then perform remote I/O.
                with factory() as read_session:
                    source=read_session.get(Source,requested_source_id)
                    if source is None: raise V1NotFoundError(f"source not found: {requested_source_id}")
                    candidate=read_session.get(Candidate,source.candidate_id)
                    if candidate is None: raise V1NotFoundError(f"candidate not found: {source.candidate_id}")
                    projection=build_source_privacy_projection(read_session,source)
                    prepared=runtime.prepare_evidence_call(read_session,source_text=projection.safe_text)
                    profile=RuntimeSettingsRepository(read_session).get_provider_profile("text_ai")
                    project_id=candidate.project_id
                with v1_session_scope(factory) as s:
                    run=start_ai_run(
                        s, task_type="evidence_extract", project_id=project_id,
                        candidate_id=candidate_id, source_id=requested_source_id,
                        provider_kind=profile.provider_type, model_name=prepared.request.model,
                        input_material=projection.safe_text, retry_count=retry_count,
                        input_safety_meta={
                            "privacy_projection":True,
                            "length_preserved":projection.redaction.length_preserved,
                            "redaction_counts":projection.redaction.counts,
                            "durable_task_id":task_id,
                        },
                    )
                    ai_run_id=run.id
                proposals=runtime.execute_evidence_call(prepared)
                proposals=rebind_privacy_safe_proposals(projection,proposals)
                # Re-check lease/cancel and persist only after the external call completes.
                with v1_session_scope(factory) as s:
                    if not _job_owned(s,job_id,worker_id,token):
                        if ai_run_id: fail_ai_run(s,ai_run_id,RuntimeError("job lease lost"),latency_ms=int((perf_counter()-started)*1000),error_code="job_lease_lost",status="cancelled")
                        return
                    task=s.get(TaskRecord,task_id)
                    if not task or task.cancel_requested:
                        if ai_run_id: fail_ai_run(s,ai_run_id,RuntimeError("task cancelled"),latency_ms=int((perf_counter()-started)*1000),error_code="task_cancelled",status="cancelled")
                        return
                    result=persist_source_claims(s,requested_source_id,proposals)
                    summary=_evidence_result(result)
                    if ai_run_id: finish_ai_run(s,ai_run_id,summary,latency_ms=int((perf_counter()-started)*1000))
                    task.progress_current=1; _task_finish(task,started,status="succeeded",result=summary); s.flush(); JobEngine(s).succeed(job_id,worker_id,token)
                return
            raw=blobs.get(str(payload.get("blob_hash") or ""))
            # Provider call intentionally happens outside any write transaction.
            with factory() as read_session:
                if task_type=="ocr": text=_ocr_bytes(read_session,secrets,raw,str(payload.get("media_type") or "image/png"))
                elif task_type=="ocr_pdf":
                    import importlib
                    fitz=importlib.import_module("fitz"); doc=fitz.open(stream=raw,filetype="pdf"); page_text=[]
                    try:
                        for page_no,page in enumerate(doc,1):
                            if page.get_text("text").strip():
                                page_text.append(f"[Page {page_no}]\n"+page.get_text("text").strip())
                            else:
                                pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
                                page_text.append(f"[Page {page_no}]\n"+_ocr_bytes(read_session,secrets,pix.tobytes("png"),"image/png"))
                    finally: doc.close()
                    text="\n\n".join(page_text).strip()
                elif task_type=="asr": text=_asr_bytes(read_session,secrets,raw,str(payload.get("filename") or "audio"),str(payload.get("media_type") or "audio/wav"))
                else: raise V1InvariantError("unsupported durable task type")
            with v1_session_scope(factory) as s:
                if not _job_owned(s,job_id,worker_id,token): return
                task=s.get(TaskRecord,task_id)
                if not task or task.cancel_requested: return
                kind="asr_transcript" if task_type=="asr" else "ocr_text"
                suffix=".transcript.txt" if task_type=="asr" else ".ocr.txt"
                derived_meta={"task_id":task_id,"derived_from":source_id}
                if task_type=="ocr_pdf":
                    import re
                    markers=list(re.finditer(r"(?m)^\[Page (\d+)\]\n",text))
                    blocks=[]
                    for idx,marker in enumerate(markers):
                        start=marker.end(); end=markers[idx+1].start()-2 if idx+1<len(markers) else len(text)
                        blocks.append({"page":int(marker.group(1)),"block_index":0,"char_start":start,"char_end":max(start,end)})
                    derived_meta["extractor"]={"format":"ocr_pdf","grounding_blocks":blocks,"grounding_version":"srw.ocr_pdf.pages.v1"}
                src=CandidateIntakeService(s).add_text_source(candidate_id,text,filename=str(payload.get("filename") or task_type)+suffix,source_kind=kind,metadata=derived_meta)
                _publish_current(s,candidate_id,src.id);task.result_source_id=src.id;task.progress_current=1;_task_finish(task,started,status="succeeded",result={"result_source_id":src.id});_sync_parent_batch_item(s,task,child_status="succeeded");s.flush();JobEngine(s).succeed(job_id,worker_id,token)
        except ProviderNotReadyError as exc:
            with v1_session_scope(factory) as s:
                if ai_run_id: fail_ai_run(s,ai_run_id,exc,latency_ms=int((perf_counter()-started)*1000),error_code="provider_not_ready",status="waiting_provider")
                if not _job_owned(s,job_id,worker_id,token): return
                task=s.get(TaskRecord,task_id);_task_finish(task,started,status="waiting_provider",error_code="provider_not_ready",error_message=str(exc));_sync_parent_batch_item(s,task,child_status="waiting_provider");s.flush();JobEngine(s).fail(job_id,worker_id,token)
        except ProviderOutputInvalidError as exc:
            with v1_session_scope(factory) as s:
                if ai_run_id: fail_ai_run(s,ai_run_id,exc,latency_ms=int((perf_counter()-started)*1000),error_code="provider_output_invalid")
                if not _job_owned(s,job_id,worker_id,token): return
                task=s.get(TaskRecord,task_id);_task_finish(task,started,status="failed",error_code="provider_output_invalid",error_message=str(exc));_sync_parent_batch_item(s,task,child_status="failed");s.flush();JobEngine(s).fail(job_id,worker_id,token)
        except Exception as exc:
            with v1_session_scope(factory) as s:
                if ai_run_id: fail_ai_run(s,ai_run_id,exc,latency_ms=int((perf_counter()-started)*1000),error_code="provider_failure")
                if not _job_owned(s,job_id,worker_id,token): return
                task=s.get(TaskRecord,task_id);_task_finish(task,started,status="failed",error_code="provider_failure",error_message=str(exc));_sync_parent_batch_item(s,task,child_status="failed");s.flush();JobEngine(s).fail(job_id,worker_id,token)

    def _run_worker_once() -> bool:
        worker_id=f"srw-{uuid.uuid4()}"
        with v1_session_scope(factory) as s:
            job=JobEngine(s).lease_next(worker_id,lease_for=__import__('datetime').timedelta(minutes=10))
            if not job: return False
            job_id=job.id;token=str(job.lease_token or "");job_type=job.type;payload=json.loads(job.payload_json or "{}")
        task_id=str(payload.get("task_id") or "")
        if not task_id: return False
        if job_type=="task.batch_candidate_intake": _process_batch_job(job_id,worker_id,token,task_id)
        else: _process_single_job(job_id,worker_id,token,task_id)
        return True

    def _requeue_job(job_id: str) -> bool:
        with v1_session_scope(factory) as s:
            job=s.get(Job,job_id)
            if not job: return False
            task_id=str(json.loads(job.payload_json or "{}").get("task_id") or "")
            task=s.get(TaskRecord,task_id) if task_id else None
            if task:
                task.cancel_requested=False;task.status="queued";task.error_code="";task.error_message=""
            return JobEngine(s).requeue(job_id)

    app.state.srw_run_worker_once=_run_worker_once
    app.state.srw_requeue_job=_requeue_job

    stop_worker=threading.Event()
    def _worker_loop():
        while not stop_worker.is_set():
            try:
                worked=_run_worker_once()
            except Exception:
                worked=False
            if not worked: stop_worker.wait(0.35)
    def _start_worker():
        if str(__import__('os').environ.get("SRW_BACKGROUND_WORKER","0")).lower() in {"1","true","yes"}:
            t=threading.Thread(target=_worker_loop,name="srw-task-worker",daemon=True);app.state.srw_worker_thread=t;t.start()
    def _stop_worker():
        stop_worker.set();t=getattr(app.state,"srw_worker_thread",None)
        if t and t.is_alive(): t.join(timeout=2.0)
    app.add_event_handler("startup",_start_worker);app.add_event_handler("shutdown",_stop_worker)

    async def tasks(r):
        status=(r.query_params.get("status") or "").strip()
        task_type=(r.query_params.get("type") or "").strip()
        candidate_id=(r.query_params.get("candidate_id") or "").strip()
        try:
            limit=min(200,max(1,int(r.query_params.get("limit","50"))))
            offset=max(0,int(r.query_params.get("offset","0")))
        except ValueError as exc:
            raise V1InvariantError("limit and offset must be integers") from exc
        filters=[]
        if status: filters.append(TaskRecord.status==status)
        if task_type: filters.append(TaskRecord.task_type==task_type)
        if candidate_id: filters.append(TaskRecord.candidate_id==candidate_id)
        with factory() as s:
            total=s.scalar(select(func.count(TaskRecord.id)).where(*filters)) or 0
            rows=s.scalars(select(TaskRecord).where(*filters).order_by(TaskRecord.created_at.desc()).limit(limit).offset(offset)).all()
            return JSONResponse({"tasks":[_task_json(x) for x in rows],"total":total,"limit":limit,"offset":offset})
    async def task_detail(r):
        tid=r.path_params["task_id"]
        with factory() as s:
            row=s.get(TaskRecord,tid)
            if not row: raise V1NotFoundError(f"task not found: {tid}")
            return JSONResponse(_task_json(row))
    async def cancel_task(r):
        tid=r.path_params["task_id"]
        with v1_session_scope(factory) as s:
            x=s.get(TaskRecord,tid)
            if not x: raise V1NotFoundError(f"task not found: {tid}")
            if x.status=="succeeded": return JSONResponse({"task_id":tid,"status":x.status})
            x.cancel_requested=True;x.status="cancelled"
            if x.job_id: JobEngine(s).cancel(x.job_id)
            return JSONResponse({"task_id":tid,"status":x.status})
    async def retry_task(r):
        tid=r.path_params["task_id"]
        with v1_session_scope(factory) as s:
            x=s.get(TaskRecord,tid)
            if not x: raise V1NotFoundError(f"task not found: {tid}")
            if x.status=="cancelled": raise V1InvariantError("cancelled task cannot be retried")
            if not x.job_id:
                job=JobEngine(s).enqueue(f"task.{x.task_type}",{"task_id":x.id},idempotency_key=f"task:{x.id}:retry:{x.attempt_count+1}")
                x.job_id=job.id
            else:
                JobEngine(s).requeue(x.job_id)
            x.cancel_requested=False;x.status="queued";x.error_code="";x.error_message="";x.finished_at=None
            return JSONResponse({"task_id":tid,"job_id":x.job_id,"status":"queued"})

    def _latest_draft(s,pid):
        return s.scalar(select(ProtocolRevision).where(ProtocolRevision.project_id==pid,ProtocolRevision.state=="draft").order_by(ProtocolRevision.revision.desc()).limit(1))

    async def templates(_r):
        with factory() as s:
            rows=s.scalars(select(RoleTemplate).order_by(RoleTemplate.updated_at.desc())).all();return JSONResponse({"templates":[{"template_id":x.id,"name":x.name,"role_title":x.role_title,"payload":json.loads(x.payload_json),"updated_at":x.updated_at.isoformat()} for x in rows]})
    async def template_create(r):
        b=await _json_body(r)
        with v1_session_scope(factory) as s:
            x=RoleTemplate(name=_s(b,"name",required=True),role_title=_s(b,"role_title"),payload_json=json.dumps(b.get("payload") if isinstance(b.get("payload"),dict) else {},ensure_ascii=False));s.add(x);s.flush();return JSONResponse({"template_id":x.id,"name":x.name})
    async def template_update(r):
        tid=r.path_params["template_id"];b=await _json_body(r)
        with v1_session_scope(factory) as s:
            x=s.get(RoleTemplate,tid)
            if not x: raise V1NotFoundError(f"template not found: {tid}")
            if "name" in b: x.name=_s(b,"name",required=True)
            if "role_title" in b: x.role_title=_s(b,"role_title")
            if "payload" in b:
                if not isinstance(b["payload"],dict): raise V1InvariantError("payload must be an object")
                x.payload_json=json.dumps(b["payload"],ensure_ascii=False)
            return JSONResponse({"template_id":x.id,"name":x.name})
    async def template_delete(r):
        tid=r.path_params["template_id"]
        with v1_session_scope(factory) as s:
            x=s.get(RoleTemplate,tid)
            if not x: raise V1NotFoundError(f"template not found: {tid}")
            s.delete(x);return JSONResponse({"deleted":True})
    async def template_from_current(r):
        pid=r.path_params["project_id"];b=await _json_body(r)
        with v1_session_scope(factory) as s:
            project=s.get(Project,pid)
            if not project: raise V1NotFoundError(f"project not found: {pid}")
            rev=_latest_draft(s,pid) or (s.get(ProtocolRevision,project.current_protocol_revision_id) if project.current_protocol_revision_id else None)
            if not rev: raise V1InvariantError("project has no protocol to save as template")
            payload=ProtocolRepository(s).get_payload(rev.id)
            role=str((payload.get("brief") or {}).get("title") or "")
            x=RoleTemplate(name=_s(b,"name",required=True),role_title=role,payload_json=json.dumps(payload,ensure_ascii=False));s.add(x);s.flush()
            return JSONResponse({"template_id":x.id,"name":x.name,"source_revision_id":rev.id})
    async def template_apply(r):
        tid=r.path_params["template_id"];pid=r.path_params["project_id"];b=await _json_body(r);mode=_s(b,"mode",default="merge")
        if mode not in {"merge","replace"}: raise V1InvariantError("mode must be merge or replace")
        with v1_session_scope(factory) as s:
            tpl=s.get(RoleTemplate,tid);project=s.get(Project,pid)
            if not tpl: raise V1NotFoundError(f"template not found: {tid}")
            if not project: raise V1NotFoundError(f"project not found: {pid}")
            draft=_latest_draft(s,pid)
            if not draft: draft=ProtocolRepository(s).fork_current_to_draft(pid)
            current=ProtocolRepository(s).get_payload(draft.id); incoming=json.loads(tpl.payload_json or "{}")
            if mode=="replace": merged=incoming
            else:
                merged=dict(current); existing=list(current.get("criteria") or []); names={str(x.get("name") or "").strip().lower() for x in existing if isinstance(x,dict)}
                for item in incoming.get("criteria") or []:
                    if isinstance(item,dict) and str(item.get("name") or "").strip().lower() not in names: existing.append(dict(item))
                merged["criteria"]=existing
            row=ProtocolRepository(s).update_draft(draft.id,merged,{"origin":"template_apply","template_id":tid,"mode":mode})
            return JSONResponse({"revision_id":row.id,"state":row.state,"mode":mode,"criteria_count":len(ProtocolRepository(s).get_payload(row.id).get("criteria") or [])})

    async def knowledge_status(_r): return JSONResponse({"databases":knowledge.status()})
    async def knowledge_search(r): return JSONResponse({"results":knowledge.search(r.query_params.get("q","")[:200],limit=min(50,max(1,int(r.query_params.get("limit","10")))))})
    async def knowledge_apply(r):
        pid=r.path_params["project_id"];b=await _json_body(r);result=b.get("result")
        if not isinstance(result,dict): raise V1InvariantError("result must be an object")
        with v1_session_scope(factory) as s:
            project=s.get(Project,pid)
            if not project: raise V1NotFoundError(f"project not found: {pid}")
            draft=_latest_draft(s,pid)
            if not draft: draft=ProtocolRepository(s).fork_current_to_draft(pid)
            payload=ProtocolRepository(s).get_payload(draft.id); criteria=list(payload.get("criteria") or [])
            criterion={"name":_s(b,"criterion_name") or str(result.get("title") or "知识建议"),"definition":str(result.get("detail") or ""),"decision_critical":bool(b.get("decision_critical",False)),"verification_required":bool(b.get("verification_required",True)),"verification_probes":[],"knowledge_source":{"database":str(result.get("database") or ""),"knowledge_id":str(result.get("knowledge_id") or ""),"title":str(result.get("title") or "")}}
            criteria.append(criterion);payload["criteria"]=criteria
            row=ProtocolRepository(s).update_draft(draft.id,payload,{"origin":"knowledge_apply","knowledge_id":criterion["knowledge_source"]["knowledge_id"]})
            saved=ProtocolRepository(s).get_payload(row.id)["criteria"][-1]
            return JSONResponse({"revision_id":row.id,"criterion":saved})

    def _parse_iso(value: str):
        if not value: return None
        try:
            from datetime import datetime
            return datetime.fromisoformat(value.replace("Z","+00:00"))
        except ValueError as exc:
            raise V1InvariantError("scheduled_at must be ISO-8601") from exc

    def _event_metadata(session, candidate_id: str, event_type: str, value: Any) -> dict[str, Any]:
        if value is None: return {}
        if not isinstance(value,dict): raise V1InvariantError("metadata must be an object")
        metadata=dict(value)
        candidate=session.get(Candidate,candidate_id)
        if candidate is None: raise V1NotFoundError(f"candidate not found: {candidate_id}")
        project=session.get(Project,candidate.project_id)
        known=set()
        if project and project.current_protocol_revision_id:
            payload=ProtocolRepository(session).get_payload(project.current_protocol_revision_id)
            known={str(x.get("criterion_key") or "") for x in (payload.get("criteria") or []) if isinstance(x,dict)}
        questions=metadata.get("questions",[])
        if questions is None: questions=[]
        if not isinstance(questions,list) or any(not isinstance(x,dict) for x in questions): raise V1InvariantError("metadata.questions must be an array of objects")
        normalized_q=[]
        for item in questions:
            key=str(item.get("criterion_key") or "").strip(); question=str(item.get("question") or "").strip(); purpose=str(item.get("purpose") or "").strip(); answer=str(item.get("answer") or "").strip()
            if not question: raise V1InvariantError("interview question is required")
            if key and known and key not in known: raise V1InvariantError(f"unknown criterion_key: {key}")
            normalized_q.append({"criterion_key":key,"question":question,"purpose":purpose,"answer":answer})
        feedback=metadata.get("feedback",[])
        if feedback is None: feedback=[]
        if not isinstance(feedback,list) or any(not isinstance(x,dict) for x in feedback): raise V1InvariantError("metadata.feedback must be an array of objects")
        ratings={"strong","acceptable","concern","unknown"}; normalized_f=[]
        for item in feedback:
            key=str(item.get("criterion_key") or "").strip(); rating=str(item.get("rating") or "unknown").strip()
            if not key: raise V1InvariantError("feedback criterion_key is required")
            if known and key not in known: raise V1InvariantError(f"unknown criterion_key: {key}")
            if rating not in ratings: raise V1InvariantError("feedback rating must be strong, acceptable, concern, or unknown")
            normalized_f.append({"criterion_key":key,"rating":rating,"observation":str(item.get("observation") or "").strip(),"supporting_evidence":str(item.get("supporting_evidence") or "").strip(),"counter_evidence":str(item.get("counter_evidence") or "").strip(),"recommendation":str(item.get("recommendation") or "").strip()})
        metadata["questions"]=normalized_q; metadata["feedback"]=normalized_f
        metadata["overall_recommendation"]=str(metadata.get("overall_recommendation") or "").strip()
        return metadata

    def _event_source_text(event: RecruitmentEvent, metadata: dict[str,Any]) -> str:
        lines=[f"Recruitment event: {event.event_type}",f"Title: {event.title}",f"Outcome: {event.outcome}"]
        if event.notes: lines += ["", "Notes:", event.notes]
        for idx,q in enumerate(metadata.get("questions") or [],1):
            lines += ["",f"Question {idx}: {q.get('question','')}",f"Criterion: {q.get('criterion_key','')}",f"Purpose: {q.get('purpose','')}",f"Answer: {q.get('answer','')}"]
        for idx,f in enumerate(metadata.get("feedback") or [],1):
            lines += ["",f"Feedback {idx} / {f.get('criterion_key','')}",f"Rating: {f.get('rating','')}",f"Observation: {f.get('observation','')}",f"Supporting evidence: {f.get('supporting_evidence','')}",f"Counter evidence: {f.get('counter_evidence','')}",f"Recommendation: {f.get('recommendation','')}"]
        if metadata.get("overall_recommendation"): lines += ["",f"Overall recommendation: {metadata['overall_recommendation']}"]
        return "\n".join(lines).strip()

    async def events(r):
        cid=r.path_params["candidate_id"]
        with factory() as s:
            rows=s.scalars(select(RecruitmentEvent).where(RecruitmentEvent.candidate_id==cid).order_by(func.coalesce(RecruitmentEvent.scheduled_at,RecruitmentEvent.created_at).desc())).all()
            return JSONResponse({"events":[{
                "event_id":x.id,"event_type":x.event_type,"title":x.title,"notes":x.notes,"source_id":x.source_id,
                "metadata":json.loads(x.metadata_json or "{}"),
                "scheduled_at":x.scheduled_at.isoformat() if x.scheduled_at else None,"duration_minutes":x.duration_minutes,
                "interviewer":x.interviewer,"location":x.location,"event_state":x.event_state,"outcome":x.outcome,
                "created_at":x.created_at.isoformat()} for x in rows]})
    async def add_event(r):
        cid=r.path_params["candidate_id"];b=await _json_body(r); et=_s(b,"event_type",required=True)
        if et not in {"phone_screen","interview","feedback","note"}: raise V1InvariantError("unsupported event_type")
        state=_s(b,"event_state",default="completed" if not b.get("scheduled_at") else "scheduled")
        if state not in {"scheduled","completed","cancelled","no_show"}: raise V1InvariantError("unsupported event_state")
        try: duration=max(0,int(b.get("duration_minutes") or 0))
        except (TypeError,ValueError) as exc: raise V1InvariantError("duration_minutes must be an integer") from exc
        with v1_session_scope(factory) as s:
            candidate=s.get(Candidate,cid)
            if not candidate: raise V1NotFoundError(f"candidate not found: {cid}")
            metadata=_event_metadata(s,cid,et,b.get("metadata",{}))
            x=RecruitmentEvent(candidate_id=cid,event_type=et,title=_s(b,"title"),notes=_s(b,"notes"),source_id=_s(b,"source_id") or None,metadata_json=json.dumps(metadata,ensure_ascii=False,separators=(",",":")),scheduled_at=_parse_iso(_s(b,"scheduled_at")),duration_minutes=duration,interviewer=_s(b,"interviewer"),location=_s(b,"location"),event_state=state,outcome=_s(b,"outcome"))
            s.add(x);s.flush()
            if state=="completed" and et in {"phone_screen","interview","feedback"} and (metadata.get("questions") or metadata.get("feedback")) and not x.source_id:
                text=_event_source_text(x,metadata); source=add_source(s,cid,source_kind=f"{et}_record",content_hash=content_hash({"event_id":x.id,"text":text}),text_content=text,media_type="text/plain",metadata={"event_id":x.id,"event_type":et,"structured":True}); _publish_current(s,cid,source.id); x.source_id=source.id
            append_audit_event(s,event_type="RECRUITMENT_EVENT_CREATED",entity_type="recruitment_event",entity_id=x.id,actor=_s(b,"actor",default="human"),payload={"event_type":et,"event_state":state,"source_id":x.source_id},project_id=candidate.project_id,candidate_id=cid)
            return JSONResponse({"event_id":x.id,"event_state":x.event_state,"source_id":x.source_id})

    async def update_event(r):
        eid=r.path_params["event_id"]; b=await _json_body(r)
        with v1_session_scope(factory) as s:
            x=s.get(RecruitmentEvent,eid)
            if not x: raise V1NotFoundError(f"event not found: {eid}")
            candidate=s.get(Candidate,x.candidate_id)
            metadata=json.loads(x.metadata_json or "{}")
            if "metadata" in b:
                metadata=_event_metadata(s,x.candidate_id,x.event_type,b.get("metadata")); x.metadata_json=json.dumps(metadata,ensure_ascii=False,separators=(",",":"))
            if "event_state" in b:
                state=_s(b,"event_state",required=True)
                if state not in {"scheduled","completed","cancelled","no_show"}: raise V1InvariantError("unsupported event_state")
                x.event_state=state
            if "outcome" in b: x.outcome=_s(b,"outcome")
            if "notes" in b: x.notes=_s(b,"notes")
            if "scheduled_at" in b: x.scheduled_at=_parse_iso(_s(b,"scheduled_at"))
            if "duration_minutes" in b:
                try: x.duration_minutes=max(0,int(b.get("duration_minutes") or 0))
                except (TypeError,ValueError) as exc: raise V1InvariantError("duration_minutes must be an integer") from exc
            if "interviewer" in b: x.interviewer=_s(b,"interviewer")
            if "location" in b: x.location=_s(b,"location")
            if x.event_state=="completed" and x.event_type in {"phone_screen","interview","feedback"} and (metadata.get("questions") or metadata.get("feedback")) and not x.source_id:
                text=_event_source_text(x,metadata); source=add_source(s,x.candidate_id,source_kind=f"{x.event_type}_record",content_hash=content_hash({"event_id":x.id,"text":text}),text_content=text,media_type="text/plain",metadata={"event_id":x.id,"event_type":x.event_type,"structured":True}); _publish_current(s,x.candidate_id,source.id); x.source_id=source.id
            append_audit_event(s,event_type="RECRUITMENT_EVENT_UPDATED",entity_type="recruitment_event",entity_id=x.id,actor=_s(b,"actor",default="human"),payload={"event_state":x.event_state,"outcome":x.outcome,"source_id":x.source_id},project_id=candidate.project_id if candidate else None,candidate_id=x.candidate_id)
            return JSONResponse({"event_id":x.id,"event_state":x.event_state,"outcome":x.outcome,"source_id":x.source_id,"metadata":metadata})

    def _judgment_payload(row):
        return {"criterion_key":row.criterion_key,"status":row.status,"evidence_level":row.evidence_level,"reason":row.reason,"gap":row.gap}

    async def reevaluations(r):
        cid=r.path_params["candidate_id"]
        with factory() as s:
            rows=s.scalars(select(ReevaluationDraft).where(ReevaluationDraft.candidate_id==cid).order_by(ReevaluationDraft.created_at.desc())).all()
            return JSONResponse({"drafts":[{"draft_id":x.id,"state":x.state,"summary":x.summary,"proposal":json.loads(x.proposal_json),"diff":json.loads(x.diff_json or "[]"),"decision_context_hash":x.decision_context_hash,"created_at":x.created_at.isoformat(),"applied_at":x.applied_at.isoformat() if x.applied_at else None} for x in rows]})

    async def reevaluation_create(r):
        from srw.modules.decision.context import get_current_decision_context
        cid=r.path_params["candidate_id"];b=await _json_body(r)
        proposal=b.get("proposal") if isinstance(b.get("proposal"),dict) else {}
        proposed=proposal.get("judgments") or []
        if not isinstance(proposed,list): raise V1InvariantError("proposal.judgments must be an array")
        with v1_session_scope(factory) as s:
            cand=s.get(Candidate,cid)
            if not cand: raise V1NotFoundError(f"candidate not found: {cid}")
            ctx=get_current_decision_context(s,cid,evaluation_policy_revision=evaluation_policy_revision)
            current={x.criterion_key:x for x in s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==cid,CriterionJudgment.decision_context_hash==ctx.hash)).all()}
            protocol=ProtocolRepository(s).get_payload(ctx.protocol_revision_id); known={str(x.get("criterion_key") or "") for x in protocol.get("criteria",[]) if isinstance(x,dict)}
            # A new MaterialRevision intentionally changes the decision context. Reevaluation must still
            # compare against the latest prior human judgment for the same stable criterion key, rather
            # than pretending the prior assessment never existed. Current-context judgments win.
            baseline=dict(current)
            previous=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==cid,CriterionJudgment.criterion_key.in_(known)).order_by(CriterionJudgment.updated_at.desc(),CriterionJudgment.id.desc())).all() if known else []
            for row in previous: baseline.setdefault(row.criterion_key,row)
            diff=[]
            for item in proposed:
                if not isinstance(item,dict): raise V1InvariantError("reevaluation judgment must be an object")
                key=str(item.get("criterion_key") or "").strip()
                if not key or key not in known: raise V1InvariantError(f"unknown criterion_key: {key}")
                before=baseline.get(key)
                before_view=_judgment_payload(before) if before else {"criterion_key":key,"status":"missing","evidence_level":"none","reason":"","gap":""}
                after={"criterion_key":key,"status":str(item.get("status") or "missing"),"evidence_level":str(item.get("evidence_level") or "none"),"reason":str(item.get("reason") or ""),"gap":str(item.get("gap") or ""),"claim_ids":[str(x) for x in (item.get("claim_ids") or [])]}
                if after["status"] not in {"met","partial","missing","conflict","not_met"}: raise V1InvariantError("invalid reevaluation status")
                if after["evidence_level"] not in {"strong","medium","weak","none"}: raise V1InvariantError("invalid reevaluation evidence_level")
                if any(before_view.get(k)!=after.get(k) for k in ("status","evidence_level","reason","gap")):
                    diff.append({"criterion_key":key,"before":before_view,"after":after})
            x=ReevaluationDraft(candidate_id=cid,summary=_s(b,"summary"),proposal_json=json.dumps(proposal,ensure_ascii=False),protocol_revision_id=ctx.protocol_revision_id,material_revision_id=ctx.material_revision_id,decision_context_hash=ctx.hash,diff_json=json.dumps(diff,ensure_ascii=False,separators=(",",":")))
            s.add(x);s.flush()
            append_audit_event(s,event_type="REEVALUATION_DRAFT_CREATED",entity_type="reevaluation",entity_id=x.id,actor=_s(b,"actor",default="human"),payload={"diff_count":len(diff),"context_hash":ctx.hash},project_id=ctx.project_id,candidate_id=cid)
            return JSONResponse({"draft_id":x.id,"state":x.state,"diff":diff,"decision_context_hash":ctx.hash})

    async def reevaluation_apply(r):
        from srw.modules.decision.context import get_current_decision_context
        from srw.modules.decision.commands import record_assessment
        did=r.path_params["draft_id"]
        with v1_session_scope(factory) as s:
            x=s.get(ReevaluationDraft,did)
            if not x: raise V1NotFoundError(f"draft not found: {did}")
            diff=json.loads(x.diff_json or "[]")
            if x.state=="applied": return JSONResponse({"draft_id":x.id,"state":"applied","applied_changes":len(diff),"idempotent":True})
            if x.state=="stale": return JSONResponse({"draft_id":x.id,"state":"stale","detail":"reevaluation context is stale"},status_code=409)
            if x.state!="draft": raise V1InvariantError("draft is not applicable")
            ctx=get_current_decision_context(s,x.candidate_id,evaluation_policy_revision=evaluation_policy_revision)
            if ctx.hash!=x.decision_context_hash:
                x.state="stale"
                return JSONResponse({"draft_id":x.id,"state":"stale","detail":"material or protocol changed; recalculate reevaluation"},status_code=409)
            before_rows=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==x.candidate_id,CriterionJudgment.decision_context_hash==ctx.hash)).all()
            before_payload=[_judgment_payload(row) for row in before_rows]
            s.add(EvaluationSnapshot(candidate_id=x.candidate_id,project_id=ctx.project_id,decision_context_hash=ctx.hash,reevaluation_id=x.id,snapshot_kind="pre_reevaluation",payload_json=json.dumps({"judgments":before_payload},ensure_ascii=False,separators=(",",":"))))
            for change in diff:
                after=change.get("after") or {}
                record_assessment(s,x.candidate_id,str(change.get("criterion_key") or ""),status=str(after.get("status") or "missing"),evidence_level=str(after.get("evidence_level") or "none"),reason=str(after.get("reason") or ""),gap=str(after.get("gap") or ""),claim_ids=[str(v) for v in (after.get("claim_ids") or [])],actor="human:reevaluation",evaluation_policy_revision=evaluation_policy_revision)
            after_rows=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==x.candidate_id,CriterionJudgment.decision_context_hash==ctx.hash)).all()
            s.add(EvaluationSnapshot(candidate_id=x.candidate_id,project_id=ctx.project_id,decision_context_hash=ctx.hash,reevaluation_id=x.id,snapshot_kind="post_reevaluation",payload_json=json.dumps({"judgments":[_judgment_payload(row) for row in after_rows]},ensure_ascii=False,separators=(",",":"))))
            x.state="applied";x.applied_at=utc_now()
            append_audit_event(s,event_type="REEVALUATION_APPLIED",entity_type="reevaluation",entity_id=x.id,actor="human",payload={"diff_count":len(diff),"context_hash":ctx.hash},project_id=ctx.project_id,candidate_id=x.candidate_id)
            return JSONResponse({"draft_id":x.id,"state":x.state,"applied_changes":len(diff),"human_decision_unchanged":True})

    async def project_status(r):
        pid=r.path_params["project_id"];b=await _json_body(r)
        with v1_session_scope(factory) as s:
            row=change_project_status(s,pid,_s(b,"status",required=True),actor=_s(b,"actor",default="human"),reason=_s(b,"reason"))
            return JSONResponse({"project_id":row.id,"status":row.status})

    async def candidate_stage(r):
        cid=r.path_params["candidate_id"];b=await _json_body(r)
        with v1_session_scope(factory) as s:
            row=change_candidate_stage(s,cid,_s(b,"stage",required=True),actor=_s(b,"actor",default="human"),reason=_s(b,"reason"))
            return JSONResponse({"candidate_id":row.id,"pipeline_stage":row.pipeline_stage})

    async def candidate_pipeline(r):
        with factory() as s: return JSONResponse(pipeline_history(s,r.path_params["candidate_id"]))

    async def project_pipeline(r):
        from datetime import datetime, timezone
        pid=r.path_params["project_id"]
        with factory() as s:
            base=project_funnel(s,pid)
            project=s.get(Project,pid)
            offer_rows=s.execute(select(OfferRecord.status,func.count(OfferRecord.id)).where(OfferRecord.project_id==pid).group_by(OfferRecord.status)).all()
            offers={status:0 for status in OFFER_STATES}
            for status,count in offer_rows: offers[str(status)]=int(count)
            now=datetime.now(timezone.utc)
            event_rows=s.execute(
                select(RecruitmentEvent,Candidate.display_name)
                .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
                .where(Candidate.project_id==pid,RecruitmentEvent.event_state=="scheduled",RecruitmentEvent.scheduled_at.is_not(None),RecruitmentEvent.scheduled_at>=now)
                .order_by(RecruitmentEvent.scheduled_at,RecruitmentEvent.id).limit(20)
            ).all()
            scheduled=[{
                "event_id":event.id,"candidate_id":event.candidate_id,"candidate_name":name,
                "event_type":event.event_type,"title":event.title,"scheduled_at":event.scheduled_at.isoformat() if event.scheduled_at else None,
                "duration_minutes":event.duration_minutes,"interviewer":event.interviewer,"location":event.location,"event_state":event.event_state
            } for event,name in event_rows]
            return JSONResponse({**base,"project_status":project.status if project else "","offers_by_status":offers,"upcoming_interviews":len(scheduled),"scheduled_events":scheduled})

    async def bulk_candidate_stage(r):
        pid=r.path_params["project_id"];b=await _json_body(r);ids=b.get("candidate_ids")
        if not isinstance(ids,list): raise V1InvariantError("candidate_ids must be an array")
        with v1_session_scope(factory) as s:
            return JSONResponse(bulk_change_candidate_stage(s,pid,ids,_s(b,"stage",required=True),actor=_s(b,"actor",default="human"),reason=_s(b,"reason")))

    def _contact_view(candidate, contact):
        return {
            "candidate_id":candidate.id,"display_name":contact.display_name if contact else candidate.display_name,
            "phone":contact.phone if contact else "","email":contact.email if contact else "",
            "user_confirmed":bool(contact.user_confirmed) if contact else False,
            "confirmed_fields":json.loads(contact.confirmed_fields_json or "[]") if contact else [],
        }

    async def candidate_contact(r):
        cid=r.path_params["candidate_id"]
        with factory() as s:
            candidate=s.get(Candidate,cid)
            if not candidate: raise V1NotFoundError(f"candidate not found: {cid}")
            contact=s.scalar(select(CandidateContact).where(CandidateContact.candidate_id==cid))
            return JSONResponse(_contact_view(candidate,contact))

    async def update_candidate_contact(r):
        cid=r.path_params["candidate_id"]; b=await _json_body(r)
        with v1_session_scope(factory) as s:
            candidate=s.get(Candidate,cid)
            if not candidate: raise V1NotFoundError(f"candidate not found: {cid}")
            contact=s.scalar(select(CandidateContact).where(CandidateContact.candidate_id==cid))
            if contact is None:
                contact=CandidateContact(candidate_id=cid,display_name=candidate.display_name)
                s.add(contact); s.flush()
            if "display_name" in b:
                name=_s(b,"display_name",required=True); contact.display_name=name; candidate.display_name=name
            if "phone" in b: contact.phone=_s(b,"phone")
            if "email" in b: contact.email=_s(b,"email")
            if "user_confirmed" in b:
                value=b.get("user_confirmed")
                if not isinstance(value,bool): raise V1InvariantError("user_confirmed must be a boolean")
                contact.user_confirmed=value
            fields=[]
            if contact.display_name: fields.append("display_name")
            if contact.phone: fields.append("phone")
            if contact.email: fields.append("email")
            contact.confirmed_fields_json=json.dumps(fields if contact.user_confirmed else [],ensure_ascii=False)
            contact.provenance_json=json.dumps({"actor":_s(b,"actor",default="human"),"source":"manual"},ensure_ascii=False)
            append_audit_event(s,event_type="CANDIDATE_CONTACT_UPDATED",entity_type="candidate",entity_id=cid,actor=_s(b,"actor",default="human"),payload={"confirmed_fields":fields,"user_confirmed":contact.user_confirmed})
            return JSONResponse(_contact_view(candidate,contact))

    async def candidate_offers(r):
        cid=r.path_params["candidate_id"]
        with factory() as s:
            if s.get(Candidate,cid) is None: raise V1NotFoundError(f"candidate not found: {cid}")
            rows=s.scalars(select(OfferRecord).where(OfferRecord.candidate_id==cid).order_by(OfferRecord.created_at.desc())).all()
            return JSONResponse({"offers":[offer_view(x) for x in rows]})

    async def create_candidate_offer(r):
        cid=r.path_params["candidate_id"];b=await _json_body(r)
        with v1_session_scope(factory) as s:
            row=create_offer(s,cid,title=_s(b,"title",required=True),compensation_note=_s(b,"compensation_note"),target_start_date=_s(b,"target_start_date"),terms=_s(b,"terms"),actor=_s(b,"actor",default="human"))
            return JSONResponse(offer_view(row))

    async def offer_status(r):
        oid=r.path_params["offer_id"];b=await _json_body(r)
        with v1_session_scope(factory) as s:
            row=change_offer_status(s,oid,_s(b,"status",required=True),actor=_s(b,"actor",default="human"),reason=_s(b,"reason"))
            return JSONResponse(offer_view(row))

    async def compare_candidates(r):
        ids=[x for x in (r.query_params.get("ids") or "").split(",") if x]
        if not 2<=len(ids)<=5: raise V1InvariantError("compare requires 2 to 5 candidate ids")
        with factory() as s:
            candidates=[s.get(Candidate,cid) for cid in ids]
            if any(c is None for c in candidates): raise V1NotFoundError("one or more candidates were not found")
            project_ids={c.project_id for c in candidates if c is not None}
            if len(project_ids)!=1: raise V1InvariantError("compare candidates must belong to the same project")
            pid=next(iter(project_ids)); project=s.get(Project,pid)
            if not project or not project.current_protocol_revision_id: raise V1InvariantError("project has no published protocol")
            protocol_id=project.current_protocol_revision_id
            payload=ProtocolRepository(s).get_payload(protocol_id)
            criteria=[{"criterion_key":str(x.get("criterion_key") or ""),"name":str(x.get("name") or ""),"decision_critical":bool(x.get("decision_critical",False))} for x in (payload.get("criteria") or []) if isinstance(x,dict)]
            contacts={x.candidate_id:x for x in s.scalars(select(CandidateContact).where(CandidateContact.candidate_id.in_(ids))).all()}
            offers_by_candidate={}
            for offer in s.scalars(select(OfferRecord).where(OfferRecord.candidate_id.in_(ids)).order_by(OfferRecord.created_at.desc(),OfferRecord.id.desc())).all():
                offers_by_candidate.setdefault(offer.candidate_id,offer)
            judgments=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id.in_(ids))).all()
            judgment_map={}
            for c in candidates:
                if c is None or not c.current_material_revision_id: continue
                expected=decision_context_hash(protocol_id,c.current_material_revision_id,evaluation_policy_revision)
                for j in judgments:
                    if j.candidate_id==c.id and j.decision_context_hash==expected:
                        judgment_map[(c.id,j.criterion_key)]=j
            rows=[]
            for c in candidates:
                contact=contacts.get(c.id); offer=offers_by_candidate.get(c.id)
                crit=[]
                for definition in criteria:
                    j=judgment_map.get((c.id,definition["criterion_key"]))
                    crit.append({**definition,"status":j.status if j else "missing","evidence_level":j.evidence_level if j else "none","reason":j.reason if j else "","gap":j.gap if j else ""})
                assessment=None
                if c.current_material_revision_id:
                    try: assessment=get_candidate_assessment(s,c.id,evaluation_policy_revision=evaluation_policy_revision)
                    except Exception: assessment=None
                rows.append({"candidate_id":c.id,"display_name":c.display_name,"pipeline_stage":c.pipeline_stage or "new","has_material":bool(c.current_material_revision_id),"contact":{"phone":contact.phone if contact else "","email":contact.email if contact else "","user_confirmed":bool(contact.user_confirmed) if contact else False},"offer_status":offer.status if offer else "","assessment":assessment,"criteria":crit})
            return JSONResponse({"project_id":pid,"protocol_revision_id":protocol_id,"evaluation_policy_revision":evaluation_policy_revision,"criteria":criteria,"candidates":rows,"note":"Comparison is limited to the same project and current protocol/material decision context. Fit is shown only when evidence is publishable; no automatic hiring decision is made."})

    async def project_audit(r):
        pid=r.path_params["project_id"]
        try:
            limit=min(200,max(1,int(r.query_params.get("limit","50")))); offset=max(0,int(r.query_params.get("offset","0")))
        except ValueError as exc: raise V1InvariantError("limit and offset must be integers") from exc
        with factory() as s:
            if s.get(Project,pid) is None: raise V1NotFoundError(f"project not found: {pid}")
            revisions=s.scalars(select(ProtocolRevision).where(ProtocolRevision.project_id==pid).order_by(ProtocolRevision.revision.desc())).all()
            candidate_ids=list(s.scalars(select(Candidate.id).where(Candidate.project_id==pid)).all())
            source_ids=list(s.scalars(select(Source.id).where(Source.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            claim_ids=list(s.scalars(select(Claim.id).where(Claim.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            judgment_ids=list(s.scalars(select(CriterionJudgment.id).where(CriterionJudgment.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            decision_ids=list(s.scalars(select(HumanDecision.id).where(HumanDecision.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            event_ids=list(s.scalars(select(RecruitmentEvent.id).where(RecruitmentEvent.candidate_id.in_(candidate_ids))).all()) if candidate_ids else []
            offer_ids=list(s.scalars(select(OfferRecord.id).where(OfferRecord.project_id==pid)).all())
            legacy_ids=[pid,*candidate_ids,*source_ids,*claim_ids,*judgment_ids,*decision_ids,*event_ids,*offer_ids]
            filt=or_(AuditEvent.project_id==pid,AuditEvent.entity_id.in_(legacy_ids))
            total=s.scalar(select(func.count(AuditEvent.id)).where(filt)) or 0
            events=s.scalars(select(AuditEvent).where(filt).order_by(AuditEvent.created_at.desc(),AuditEvent.id.desc()).limit(limit).offset(offset)).all()
            return JSONResponse({
                "protocol_revisions":[{"revision_id":x.id,"revision":x.revision,"state":x.state,"created_at":x.created_at.isoformat(),"published_at":x.published_at.isoformat() if x.published_at else None,"content_hash":x.content_hash} for x in revisions],
                "audit_events":[{"event_id":x.id,"event_type":x.event_type,"entity_type":x.entity_type,"entity_id":x.entity_id,"project_id":x.project_id,"candidate_id":x.candidate_id,"actor":x.actor,"reason":x.reason,"created_at":x.created_at.isoformat()} for x in events],
                "total":int(total),"limit":limit,"offset":offset,
            })

    async def candidates_csv(r):
        import csv
        from io import StringIO
        from datetime import datetime, timezone
        pid=r.path_params["project_id"]
        def safe_cell(value):
            text="" if value is None else str(value)
            return "'"+text if text[:1] in ("=","+","-","@") else text
        with factory() as s:
            project=s.get(Project,pid)
            if project is None: raise V1NotFoundError(f"project not found: {pid}")
            protocol_id=project.current_protocol_revision_id or ""
            protocol_payload=ProtocolRepository(s).get_payload(protocol_id) if protocol_id else {"criteria":[]}
            definitions=[x for x in (protocol_payload.get("criteria") or []) if isinstance(x,dict)]
            rows=s.scalars(select(Candidate).where(Candidate.project_id==pid).order_by(Candidate.created_at,Candidate.id)).all()
            ids=[x.id for x in rows]
            contacts={x.candidate_id:x for x in s.scalars(select(CandidateContact).where(CandidateContact.candidate_id.in_(ids))).all()} if ids else {}
            offers_by_candidate={}
            if ids:
                for offer in s.scalars(select(OfferRecord).where(OfferRecord.candidate_id.in_(ids)).order_by(OfferRecord.created_at.desc(),OfferRecord.id.desc())).all(): offers_by_candidate.setdefault(offer.candidate_id,offer)
            all_j=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id.in_(ids))).all() if ids else []
            by_candidate={}
            for x in rows:
                if not protocol_id or not x.current_material_revision_id: continue
                h=decision_context_hash(protocol_id,x.current_material_revision_id,evaluation_policy_revision)
                by_candidate[x.id]={j.criterion_key:j for j in all_j if j.candidate_id==x.id and j.decision_context_hash==h}
            generated=datetime.now(timezone.utc).isoformat()
            fields=["candidate_id","display_name","pipeline_stage","archived","has_material","phone","email","contact_confirmed","offer_status","protocol_revision_id","evaluation_policy_revision","criteria_summary","evidence_gaps","created_at","generated_at"]
            out=StringIO(); w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
            for x in rows:
                contact=contacts.get(x.id); offer=offers_by_candidate.get(x.id); js=by_candidate.get(x.id,{})
                summaries=[]; gaps=[]
                for d in definitions:
                    key=str(d.get("criterion_key") or ""); name=str(d.get("name") or key); j=js.get(key)
                    status=j.status if j else "missing"; evidence=j.evidence_level if j else "none"
                    summaries.append(f"{name}:{status}/{evidence}")
                    if not j or j.gap: gaps.append(f"{name}:{j.gap if j and j.gap else '待核实'}")
                w.writerow({"candidate_id":x.id,"display_name":safe_cell(x.display_name),"pipeline_stage":x.pipeline_stage or "new","archived":int(x.archived),"has_material":int(bool(x.current_material_revision_id)),"phone":safe_cell(contact.phone if contact else ""),"email":safe_cell(contact.email if contact else ""),"contact_confirmed":int(bool(contact.user_confirmed)) if contact else 0,"offer_status":offer.status if offer else "","protocol_revision_id":protocol_id,"evaluation_policy_revision":evaluation_policy_revision,"criteria_summary":safe_cell(" | ".join(summaries)),"evidence_gaps":safe_cell(" | ".join(gaps)),"created_at":x.created_at.isoformat(),"generated_at":generated})
            return PlainTextResponse(out.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="candidates-{pid}.csv"'})

    async def job_setup(r):
        pid=r.path_params["project_id"]; body=await _json_body(r)
        with v1_session_scope(factory) as s: return JSONResponse(update_job_setup(s,pid,body))

    async def job_setup_suggest(r):
        pid=r.path_params["project_id"]
        with v1_session_scope(factory) as s: return JSONResponse(suggest_job_setup(s,pid))

    async def candidate_action_plan(r):
        cid=r.path_params["candidate_id"]
        if r.method=="GET":
            with factory() as s:
                row=s.scalar(select(CandidateActionPlan).where(CandidateActionPlan.candidate_id==cid))
                if row is None:
                    candidate=s.get(Candidate,cid)
                    if candidate is None: raise V1NotFoundError(f"candidate not found: {cid}")
                    return JSONResponse({"candidate_id":cid,"project_id":candidate.project_id,"priority":"normal","owner":"","contact_status":"to_contact","next_contact_at":None,"reason":"","last_result":""})
                return JSONResponse(action_plan_view(row))
        body=await _json_body(r)
        with v1_session_scope(factory) as s: return JSONResponse(action_plan_view(upsert_action_plan(s,cid,body)))

    async def project_contact_queue(r):
        try: limit=min(200,max(1,int(r.query_params.get("limit","50"))));offset=max(0,int(r.query_params.get("offset","0")))
        except ValueError as exc: raise V1InvariantError("limit and offset must be integers") from exc
        with factory() as s: return JSONResponse(contact_queue(s,r.path_params["project_id"],limit=limit,offset=offset))

    async def candidate_phone_script(r):
        with factory() as s: return JSONResponse(phone_script(s,r.path_params["candidate_id"],evaluation_policy_revision=evaluation_policy_revision))

    async def event_scorecards(r):
        eid=r.path_params["event_id"]
        if r.method=="GET":
            with factory() as s: return JSONResponse(scorecards_view(s,eid))
        body=await _json_body(r)
        with v1_session_scope(factory) as s:
            row=submit_scorecard(s,eid,body)
            return JSONResponse({"scorecard_id":row.id,"event_id":row.event_id,"evaluator":row.evaluator,"state":row.state,"recommendation":row.recommendation})

    def _brief_payload(s,cid):
        candidate=s.get(Candidate,cid)
        if candidate is None: raise V1NotFoundError(f"candidate not found: {cid}")
        project=s.get(Project,candidate.project_id)
        protocol_id=project.current_protocol_revision_id if project else None
        ctx_hash=""
        judgments=[]
        if protocol_id and candidate.current_material_revision_id:
            ctx=get_current_decision_context(s,cid,evaluation_policy_revision=evaluation_policy_revision);ctx_hash=ctx.hash
            judgments=s.scalars(select(CriterionJudgment).where(CriterionJudgment.candidate_id==cid,CriterionJudgment.decision_context_hash==ctx.hash)).all()
        contact=s.scalar(select(CandidateContact).where(CandidateContact.candidate_id==cid))
        plan=s.scalar(select(CandidateActionPlan).where(CandidateActionPlan.candidate_id==cid))
        return {"candidate_id":cid,"project_id":candidate.project_id,"display_name":candidate.display_name,"pipeline_stage":candidate.pipeline_stage or "new","contact":{"phone":contact.phone if contact else "","email":contact.email if contact else "","user_confirmed":bool(contact.user_confirmed) if contact else False},"action_plan":action_plan_view(plan) if plan else None,"criteria":[{"criterion_key":j.criterion_key,"status":j.status,"evidence_level":j.evidence_level,"reason":j.reason,"gap":j.gap} for j in judgments],"version_context":{"protocol_revision_id":protocol_id or "","material_revision_id":candidate.current_material_revision_id or "","evaluation_policy_revision":evaluation_policy_revision,"decision_context_hash":ctx_hash}}

    async def candidate_brief(r):
        with factory() as s: return JSONResponse(_brief_payload(s,r.path_params["candidate_id"]))

    async def project_handoff(r):
        pid=r.path_params["project_id"]
        with factory() as s:
            rows=s.scalars(select(Candidate).where(Candidate.project_id==pid,Candidate.archived.is_(False)).order_by(Candidate.created_at)).all()
            project=s.get(Project,pid)
            return JSONResponse({"project_id":pid,"project_title":project.title if project else "","generated_at":utc_now().isoformat(),"candidates":[_brief_payload(s,x.id) for x in rows]})

    async def contact_list_csv(r):
        import csv
        from io import StringIO
        pid=r.path_params["project_id"]
        def safe_cell(value):
            text="" if value is None else str(value)
            return "'"+text if text[:1] in ("=","+","-","@") else text
        with factory() as s:
            q=contact_queue(s,pid,limit=10000,offset=0)
            out=StringIO();fields=["candidate_id","display_name","phone","email","priority","contact_status","next_contact_at","next_action"]
            w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
            for x in q["candidates"]:
                w.writerow({"candidate_id":x["candidate_id"],"display_name":safe_cell(x["display_name"]),"phone":safe_cell(x["phone"]),"email":safe_cell(x["email"]),"priority":x["priority"],"contact_status":x["contact_status"],"next_contact_at":safe_cell(x["next_contact_at"] or ""),"next_action":safe_cell(x["reason"] or "联系并核实未决条件")})
            return PlainTextResponse(out.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="contact-list-{pid}.csv"'})

    async def backups(_r):
        p=create_backup(data_dir,database_path);return JSONResponse({"filename":p.name,"size_bytes":p.stat().st_size})
    async def backup_list(_r):
        root=data_dir/"backups"; root.mkdir(parents=True,exist_ok=True);return JSONResponse({"backups":[{"filename":p.name,"size_bytes":p.stat().st_size} for p in sorted(root.glob("*.zip"),reverse=True)]})
    async def backup_download(r):
        name=Path(r.path_params["filename"]).name;p=data_dir/"backups"/name
        if not p.is_file(): raise HTTPException(404)
        return FileResponse(p,filename=name)
    async def schedule_restore(r):
        import hashlib, sqlite3, tempfile, zipfile
        name=Path(r.path_params["filename"]).name
        p=data_dir/"backups"/name
        if not p.is_file(): raise HTTPException(404)
        try:
            if p.stat().st_size > 512*1024*1024: raise V1InvariantError("backup exceeds 512 MB compressed limit")
            with zipfile.ZipFile(p,"r") as z:
                infos=z.infolist();names=[x.filename for x in infos]
                if len(names)!=len(set(names)): raise V1InvariantError("backup contains duplicate ZIP members")
                if "data/srw_v1.db" not in names: raise V1InvariantError("backup does not contain data/srw_v1.db")
                total_uncompressed=0
                for info in infos:
                    n=info.filename;pp=Path(n)
                    if pp.is_absolute() or ".." in pp.parts: raise V1InvariantError("backup contains an unsafe path")
                    if info.file_size > 768*1024*1024: raise V1InvariantError("backup member exceeds 768 MB limit")
                    total_uncompressed += int(info.file_size)
                    if total_uncompressed > 1024*1024*1024: raise V1InvariantError("backup exceeds 1 GB uncompressed limit")
                raw=z.read("data/srw_v1.db")
            if raw[:16] != b"SQLite format 3\x00": raise V1InvariantError("backup database is not valid SQLite")
            with tempfile.TemporaryDirectory(prefix="srw-restore-validate-") as td:
                candidate_db=Path(td)/"restore.db"; candidate_db.write_bytes(raw)
                conn=sqlite3.connect(str(candidate_db))
                try:
                    qc=conn.execute("PRAGMA quick_check").fetchone()
                    if not qc or str(qc[0]).lower()!="ok": raise V1InvariantError("backup database failed SQLite quick_check")
                    row=conn.execute("SELECT schema_revision FROM v1_schema_meta LIMIT 1").fetchone()
                    if not row: raise V1InvariantError("backup database has no SRW schema revision")
                    schema_revision=str(row[0])
                finally: conn.close()
            current_n=int(V1_SCHEMA_REVISION.split("_")[-1]); allowed={f"v1_{i:04d}" for i in range(1,current_n+1)}
            if schema_revision not in allowed: raise V1InvariantError(f"backup schema is not compatible: {schema_revision}")
        except V1InvariantError: raise
        except (zipfile.BadZipFile,sqlite3.DatabaseError,OSError) as exc:
            raise V1InvariantError(f"backup validation failed: {exc}") from exc
        marker=data_dir/"pending_restore.json"
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        marker.write_text(json.dumps({"backup":name,"sha256":digest,"schema_revision":schema_revision},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        return JSONResponse({"scheduled":True,"filename":name,"sha256":digest,"schema_revision":schema_revision,"restart_required":True})

    async def cancel_restore(_r):
        marker=data_dir/"pending_restore.json"
        if marker.exists(): marker.unlink()
        return JSONResponse({"scheduled":False})

    async def diag(_r):
        with factory() as s:
            rel=get_release_state();return JSONResponse(diagnostics(s,data_dir=data_dir,knowledge_dir=knowledge_dir,database_path=database_path,frontend_dist=frontend_dist,version=rel["version"],schema_revision=V1_SCHEMA_REVISION))

    async def diag_export(_r):
        with factory() as s:
            rel=get_release_state()
            payload=diagnostics(s,data_dir=data_dir,knowledge_dir=knowledge_dir,database_path=database_path,frontend_dist=frontend_dist,version=rel["version"],schema_revision=V1_SCHEMA_REVISION)
            raw=build_privacy_safe_diagnostic_bundle(payload,rel)
        headers={"Content-Disposition":f'attachment; filename="srw-diagnostics-{rel["version"]}.zip"',"Cache-Control":"no-store"}
        return Response(raw,media_type="application/zip",headers=headers)

    routes=[
      Route('/api/v1/dashboard',dashboard, methods=['GET']),
      Route('/api/v1/settings/providers',provider_settings, methods=['GET']),Route('/api/v1/settings/providers/{name:str}',provider_update, methods=['PATCH']),Route('/api/v1/settings/providers/{name:str}/test',provider_probe, methods=['POST']),
      Route('/api/v1/projects/{project_id:str}/candidates',list_candidates, methods=['GET']),Route('/api/v1/projects/{project_id:str}/candidates',add_candidate, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/summary',candidate_summary, methods=['GET']),Route('/api/v1/projects/{project_id:str}/candidate-search',candidate_search, methods=['GET']),Route('/api/v1/projects/{project_id:str}/cockpit',cockpit, methods=['GET']),
      Route('/api/v1/projects/{project_id:str}/status',project_status, methods=['POST']),Route('/api/v1/projects/{project_id:str}/pipeline',project_pipeline, methods=['GET']),
      Route('/api/v1/projects/{project_id:str}/candidates/stage',bulk_candidate_stage, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/stage',candidate_stage, methods=['POST']),Route('/api/v1/candidates/{candidate_id:str}/pipeline',candidate_pipeline, methods=['GET']),
      Route('/api/v1/candidates/{candidate_id:str}/contact',candidate_contact, methods=['GET']),Route('/api/v1/candidates/{candidate_id:str}/contact',update_candidate_contact, methods=['PATCH']),
      Route('/api/v1/candidates/{candidate_id:str}/offers',candidate_offers, methods=['GET']),Route('/api/v1/candidates/{candidate_id:str}/offers',create_candidate_offer, methods=['POST']),Route('/api/v1/offers/{offer_id:str}/status',offer_status, methods=['POST']),
      Route('/api/v1/projects/{project_id:str}/candidates/batch-intake',batch_intake, methods=['POST']),
      Route('/api/v1/projects/{project_id:str}/archive',archive_project, methods=['POST']),Route('/api/v1/projects/{project_id:str}/restore',restore_project, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/archive',archive_candidate, methods=['POST']),Route('/api/v1/candidates/{candidate_id:str}/restore',restore_candidate, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/files',ingest_file, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/evidence/extract-task',extract_evidence_task, methods=['POST']),
      Route('/api/v1/tasks',tasks, methods=['GET']),Route('/api/v1/tasks/{task_id:str}',task_detail, methods=['GET']),Route('/api/v1/tasks/{task_id:str}/retry',retry_task, methods=['POST']),Route('/api/v1/tasks/{task_id:str}/cancel',cancel_task, methods=['POST']),
      Route('/api/v1/templates',templates, methods=['GET']),Route('/api/v1/templates',template_create, methods=['POST']),Route('/api/v1/templates/{template_id:str}',template_delete, methods=['DELETE']),Route('/api/v1/templates/{template_id:str}',template_update, methods=['PATCH']),Route('/api/v1/projects/{project_id:str}/templates/from-current',template_from_current, methods=['POST']),Route('/api/v1/templates/{template_id:str}/apply/{project_id:str}',template_apply, methods=['POST']),
      Route('/api/v1/knowledge/status',knowledge_status, methods=['GET']),Route('/api/v1/knowledge/search',knowledge_search, methods=['GET']),Route('/api/v1/projects/{project_id:str}/knowledge/apply',knowledge_apply, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/events',events, methods=['GET']),Route('/api/v1/candidates/{candidate_id:str}/events',add_event, methods=['POST']),
      Route('/api/v1/events/{event_id:str}',update_event, methods=['PATCH']),
      Route('/api/v1/candidates/{candidate_id:str}/reevaluations',reevaluations, methods=['GET']),Route('/api/v1/candidates/{candidate_id:str}/reevaluations',reevaluation_create, methods=['POST']),Route('/api/v1/reevaluations/{draft_id:str}/apply',reevaluation_apply, methods=['POST']),
      Route('/api/v1/candidates/compare',compare_candidates, methods=['GET']),
      Route('/api/v1/projects/{project_id:str}/audit',project_audit, methods=['GET']),Route('/api/v1/projects/{project_id:str}/candidates.csv',candidates_csv, methods=['GET']),
      Route('/api/v1/projects/{project_id:str}/job-setup',job_setup,methods=['PATCH']),Route('/api/v1/projects/{project_id:str}/job-setup/suggest',job_setup_suggest,methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/action-plan',candidate_action_plan,methods=['GET','PATCH']),Route('/api/v1/projects/{project_id:str}/contact-queue',project_contact_queue,methods=['GET']),Route('/api/v1/candidates/{candidate_id:str}/phone-script',candidate_phone_script,methods=['GET']),
      Route('/api/v1/events/{event_id:str}/scorecards',event_scorecards,methods=['GET','POST']),
      Route('/api/v1/candidates/{candidate_id:str}/brief',candidate_brief,methods=['GET']),Route('/api/v1/projects/{project_id:str}/handoff',project_handoff,methods=['GET']),Route('/api/v1/projects/{project_id:str}/contact-list.csv',contact_list_csv,methods=['GET']),
      Route('/api/v1/system/backups',backups, methods=['POST']),Route('/api/v1/system/backups',backup_list, methods=['GET']),Route('/api/v1/system/backups/{filename:str}',backup_download, methods=['GET']),Route('/api/v1/system/backups/{filename:str}/restore',schedule_restore, methods=['POST']),Route('/api/v1/system/restore/cancel',cancel_restore, methods=['POST']),Route('/api/v1/system/diagnostics',diag, methods=['GET']),Route('/api/v1/system/diagnostics/export',diag_export, methods=['GET']),
    ]
    app.routes.extend(routes)
