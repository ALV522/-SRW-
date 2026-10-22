from __future__ import annotations

import base64, json, mimetypes, threading, time, uuid
from time import perf_counter
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from srw.evidence.pipeline import extract_source_claims, persist_source_claims
from srw.api.http_utils import body_dict as _body_dict, json_body as _json_body, s_field as _s
from srw.api.routes.interviews import interview_routes
from srw.api.routes.operations import operation_routes
from srw.api.routes.system import system_routes
from srw.api.routes.providers import provider_routes
from srw.api.routes.decisions import reevaluation_routes
from srw.api.routes.candidates import candidate_routes
from srw.api.routes.projects import project_routes
from srw.api.routes.reporting import reporting_routes
from srw.api.provider_support import api_key_name as _key_for, httpx_module as _httpx, profile_view as _profile_view, probe_provider as _probe
from srw.api.shared import latest_draft as _latest_draft
from srw.api.shared import publish_current_revision as _publish_current
from srw.api.routes.offers import offer_routes
from srw.intake.service import CandidateIntakeService
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash, decision_context_hash
from srw.modules.audit.models import AuditEvent
from srw.modules.audit.repository import append_audit_event
from srw.modules.ai_runs.service import start_ai_run, finish_ai_run, fail_ai_run
from srw.modules.candidate.commands import add_source, create_candidate
from srw.modules.candidate.models import Candidate, Claim, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.modules.identity.models import CandidateIdentityReview
from srw.modules.calibration.models import JudgmentReviewItem
from srw.modules.fullworkbench import BlobStore, KnowledgeService, RecruitmentEvent, ReevaluationDraft, TaskRecord
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.recruiting.models import CandidateStageTransition, OfferRecord
from srw.modules.recruiting.operations_models import CandidateActionPlan, InterviewScorecardSubmission
from srw.recruiting.workbench import (upsert_action_plan, action_plan_view, phone_script)
from srw.recruiting.operations import (
    PIPELINE_STAGES, OFFER_STATES, bulk_change_candidate_stage, change_candidate_stage,
    pipeline_history, project_funnel,
)
from srw.providers.contracts import ProviderFailureError, ProviderNotReadyError, ProviderOutputInvalidError
from srw.providers.runtime import ProviderRuntime
from srw.privacy.service import build_source_privacy_projection, rebind_privacy_safe_proposals
from srw.runtime.db.session import v1_session_scope
from srw.runtime.jobs.engine import JobEngine
from srw.runtime.jobs.models import Job
from srw.runtime.settings import RuntimeSettingsRepository
from srw.surfaces.workbench import get_workbench
from srw.surfaces.daily_queue import local_day_end_utc



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
                "candidates":s.scalar(
                    select(func.count(Candidate.id))
                    .join(Project,Project.id==Candidate.project_id)
                    .where(Candidate.archived.is_(False),Project.status!="archived")
                ) or 0,
                "open_tasks":s.scalar(select(func.count(TaskRecord.id)).where(TaskRecord.status.in_(("queued","running","waiting_provider","failed")))) or 0,
                "unreviewed_claims":s.scalar(
                    select(func.count(Claim.id))
                    .join(Candidate,Candidate.id==Claim.candidate_id)
                    .join(Project,Project.id==Candidate.project_id)
                    .where(Claim.confirmation_state=="unreviewed",Candidate.archived.is_(False),Project.status!="archived")
                ) or 0,
            }
            req_rows=s.execute(select(Project.status,func.count(Project.id)).group_by(Project.status)).all()
            requisitions={str(status):int(count) for status,count in req_rows}
            stage_rows=s.execute(
                select(Candidate.pipeline_stage,func.count(Candidate.id))
                .join(Project,Project.id==Candidate.project_id)
                .where(Candidate.archived.is_(False),Project.status!="archived")
                .group_by(Candidate.pipeline_stage)
            ).all()
            candidates_by_stage={stage:0 for stage in PIPELINE_STAGES}
            for stage,count in stage_rows: candidates_by_stage[str(stage or "new")]=int(count)
            offer_rows=s.execute(
                select(OfferRecord.status,func.count(OfferRecord.id))
                .join(Project,Project.id==OfferRecord.project_id)
                .join(Candidate,Candidate.id==OfferRecord.candidate_id)
                .where(Project.status!="archived",Candidate.archived.is_(False))
                .group_by(OfferRecord.status)
            ).all()
            offers_by_status={stage:0 for stage in OFFER_STATES}
            for status,count in offer_rows: offers_by_status[str(status)]=int(count)
            now=datetime.now(timezone.utc); horizon=now+timedelta(days=14)
            upcoming=s.scalar(
                select(func.count(RecruitmentEvent.id))
                .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
                .join(Project,Project.id==Candidate.project_id)
                .where(
                    RecruitmentEvent.event_state=="scheduled",
                    RecruitmentEvent.scheduled_at.is_not(None),
                    RecruitmentEvent.scheduled_at>=now,
                    RecruitmentEvent.scheduled_at<=horizon,
                    Candidate.archived.is_(False),Project.status!="archived",
                )
            ) or 0
            recent=[{"event_type":x.event_type,"entity_type":x.entity_type,"entity_id":x.entity_id,"actor":x.actor,"created_at":x.created_at.isoformat()} for x in s.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(12)).all()]
            overdue=s.scalar(
                select(func.count(CandidateActionPlan.id))
                .join(Candidate,Candidate.id==CandidateActionPlan.candidate_id)
                .join(Project,Project.id==CandidateActionPlan.project_id)
                .where(
                    CandidateActionPlan.next_contact_at.is_not(None),
                    CandidateActionPlan.next_contact_at<now,
                    CandidateActionPlan.contact_status.in_(("to_contact","callback","attempted")),
                    Candidate.archived.is_(False),
                    Project.status!="archived",
                )
            ) or 0
            today_end=local_day_end_utc(now)
            today_contacts=s.scalar(
                select(func.count(CandidateActionPlan.id))
                .join(Candidate,Candidate.id==CandidateActionPlan.candidate_id)
                .join(Project,Project.id==CandidateActionPlan.project_id)
                .where(
                    CandidateActionPlan.next_contact_at.is_not(None),
                    CandidateActionPlan.next_contact_at>=now,
                    CandidateActionPlan.next_contact_at<today_end,
                    CandidateActionPlan.contact_status.in_(("to_contact","callback","attempted")),
                    Candidate.archived.is_(False),
                    Project.status!="archived",
                )
            ) or 0
            pending_scorecards=s.scalar(
                select(func.count(RecruitmentEvent.id))
                .join(Candidate,Candidate.id==RecruitmentEvent.candidate_id)
                .join(Project,Project.id==Candidate.project_id)
                .where(
                    RecruitmentEvent.event_state=="completed",
                    RecruitmentEvent.event_type=="interview",
                    ~RecruitmentEvent.id.in_(select(InterviewScorecardSubmission.event_id).where(InterviewScorecardSubmission.state=="submitted")),
                    Candidate.archived.is_(False),
                    Project.status!="archived",
                )
            ) or 0
            stale_reevaluations=s.scalar(
                select(func.count(ReevaluationDraft.id))
                .join(Candidate,Candidate.id==ReevaluationDraft.candidate_id)
                .join(Project,Project.id==Candidate.project_id)
                .where(ReevaluationDraft.state=="stale",Candidate.archived.is_(False),Project.status!="archived")
            ) or 0
            pending_identity=s.scalar(
                select(func.count(CandidateIdentityReview.id))
                .join(Project,Project.id==CandidateIdentityReview.project_id)
                .where(CandidateIdentityReview.status=="pending",Project.status!="archived")
            ) or 0
            open_judgment_reviews=s.scalar(
                select(func.count(JudgmentReviewItem.id))
                .join(Project,Project.id==JudgmentReviewItem.project_id)
                .where(JudgmentReviewItem.state=="open",Project.status!="archived")
            ) or 0
            review_items=[]
            identity_rows=s.scalars(
                select(CandidateIdentityReview)
                .join(Project,Project.id==CandidateIdentityReview.project_id)
                .where(CandidateIdentityReview.status=="pending",Project.status!="archived")
                .order_by(CandidateIdentityReview.created_at.asc(),CandidateIdentityReview.id)
                .limit(4)
            ).all()
            for review in identity_rows:
                project=s.get(Project,review.project_id)
                candidate_a=s.get(Candidate,review.candidate_a_id)
                candidate_b=s.get(Candidate,review.candidate_b_id)
                review_items.append({
                    "kind":"identity_review",
                    "project_id":review.project_id,
                    "project_title":project.title if project else "",
                    "candidate_id":"",
                    "candidate_name":"",
                    "review_id":review.id,
                    "claim_id":"",
                    "title":"候选人身份复核",
                    "detail":f"{candidate_a.display_name if candidate_a else review.candidate_a_id} ↔ {candidate_b.display_name if candidate_b else review.candidate_b_id} · {review.match_reason}",
                })
            judgment_rows=s.execute(
                select(JudgmentReviewItem,Project.title,Candidate.display_name)
                .join(Project,Project.id==JudgmentReviewItem.project_id)
                .outerjoin(Candidate,Candidate.id==JudgmentReviewItem.candidate_id)
                .where(JudgmentReviewItem.state=="open",Project.status!="archived")
                .order_by(JudgmentReviewItem.created_at.asc(),JudgmentReviewItem.id)
                .limit(4)
            ).all()
            for review,project_title,candidate_name in judgment_rows:
                review_items.append({
                    "kind":"judgment_review",
                    "project_id":review.project_id,
                    "project_title":project_title,
                    "candidate_id":review.candidate_id or "",
                    "candidate_name":candidate_name or "",
                    "review_id":review.id,
                    "claim_id":"",
                    "title":"判断纠错复核",
                    "detail":f"{review.criterion_key} · {review.before} → {review.after} · {review.reason}",
                })
            claim_rows=s.execute(
                select(Claim,Candidate.display_name,Project.id,Project.title)
                .join(Candidate,Candidate.id==Claim.candidate_id)
                .join(Project,Project.id==Candidate.project_id)
                .where(Claim.confirmation_state=="unreviewed",Candidate.archived.is_(False),Project.status!="archived")
                .order_by(Claim.created_at.asc(),Claim.id)
                .limit(6)
            ).all()
            for claim,candidate_name,project_id,project_title in claim_rows:
                review_items.append({
                    "kind":"unreviewed_claim",
                    "project_id":project_id,
                    "project_title":project_title,
                    "candidate_id":claim.candidate_id,
                    "candidate_name":candidate_name,
                    "review_id":"",
                    "claim_id":claim.id,
                    "title":"待确认事实",
                    "detail":claim.normalized_text[:180],
                })
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
                .limit(4)
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
            today_contact_rows=s.execute(
                select(CandidateActionPlan,Candidate.display_name,Project.title)
                .join(Candidate,Candidate.id==CandidateActionPlan.candidate_id)
                .join(Project,Project.id==CandidateActionPlan.project_id)
                .where(
                    CandidateActionPlan.next_contact_at.is_not(None),
                    CandidateActionPlan.next_contact_at>=now,
                    CandidateActionPlan.next_contact_at<today_end,
                    CandidateActionPlan.contact_status.in_(("to_contact","callback","attempted")),
                    Candidate.archived.is_(False),
                    Project.status!="archived",
                )
                .order_by(CandidateActionPlan.next_contact_at.asc(),CandidateActionPlan.id)
                .limit(4)
            ).all()
            for plan,candidate_name,project_title in today_contact_rows:
                operational_items.append({
                    "kind":"today_contact",
                    "project_id":plan.project_id,
                    "project_title":project_title,
                    "candidate_id":plan.candidate_id,
                    "candidate_name":candidate_name,
                    "event_id":"",
                    "title":"今日联系",
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
                .limit(4)
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
            operational_items.sort(key=lambda x: (
                {"overdue_contact":0,"pending_interview_feedback":1,"today_contact":2}.get(x["kind"],99),
                x.get("detail",""),x.get("candidate_id",""),
            ))
            workbench=get_workbench(s,evaluation_policy_revision=evaluation_policy_revision)
            return JSONResponse({
                "metrics":metrics,"recent":recent,"recent_activity":recent,
                "requisitions_by_status":requisitions,
                "candidates_by_stage":candidates_by_stage,
                "offers_by_status":offers_by_status,
                "upcoming_interviews":int(upcoming),
                "evidence_review_backlog":int(metrics["unreviewed_claims"]),
                "operational_todos":{"overdue_contacts":int(overdue),"today_contacts":int(today_contacts),"pending_interview_feedback":int(pending_scorecards),"stale_reevaluations":int(stale_reevaluations),"pending_identity_reviews":int(pending_identity),"open_judgment_reviews":int(open_judgment_reviews)},
                "review_queue":{
                    "items":review_items[:14],
                    "total":int(pending_identity)+int(open_judgment_reviews)+int(metrics["unreviewed_claims"]),
                    "identity_count":int(pending_identity),
                    "judgment_count":int(open_judgment_reviews),
                    "claim_count":int(metrics["unreviewed_claims"]),
                },
                "operational_queue":{"items":operational_items[:12],"total":int(overdue)+int(today_contacts)+int(pending_scorecards)},
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

    async def candidate_stage(r):
        cid=r.path_params["candidate_id"];b=await _json_body(r)
        with v1_session_scope(factory) as s:
            row=change_candidate_stage(s,cid,_s(b,"stage",required=True),actor=_s(b,"actor",default="human"),reason=_s(b,"reason"))
            return JSONResponse({"candidate_id":row.id,"pipeline_stage":row.pipeline_stage})

    async def candidate_pipeline(r):
        with factory() as s: return JSONResponse(pipeline_history(s,r.path_params["candidate_id"]))

    async def bulk_candidate_stage(r):
        pid=r.path_params["project_id"];b=await _json_body(r);ids=b.get("candidate_ids")
        if not isinstance(ids,list): raise V1InvariantError("candidate_ids must be an array")
        with v1_session_scope(factory) as s:
            return JSONResponse(bulk_change_candidate_stage(s,pid,ids,_s(b,"stage",required=True),actor=_s(b,"actor",default="human"),reason=_s(b,"reason")))

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

    async def candidate_phone_script(r):
        with factory() as s: return JSONResponse(phone_script(s,r.path_params["candidate_id"],evaluation_policy_revision=evaluation_policy_revision))


    routes=[
      Route('/api/v1/dashboard',dashboard, methods=['GET']),
      *provider_routes(factory=factory, secrets=secrets),
      *candidate_routes(factory=factory),
      
      
      Route('/api/v1/projects/{project_id:str}/candidates/stage',bulk_candidate_stage, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/stage',candidate_stage, methods=['POST']),Route('/api/v1/candidates/{candidate_id:str}/pipeline',candidate_pipeline, methods=['GET']),
      
      *offer_routes(factory=factory),
      Route('/api/v1/projects/{project_id:str}/candidates/batch-intake',batch_intake, methods=['POST']),
      *project_routes(factory=factory),
      
      Route('/api/v1/candidates/{candidate_id:str}/files',ingest_file, methods=['POST']),
      Route('/api/v1/candidates/{candidate_id:str}/evidence/extract-task',extract_evidence_task, methods=['POST']),
      *operation_routes(factory=factory),
      
      Route('/api/v1/knowledge/status',knowledge_status, methods=['GET']),Route('/api/v1/knowledge/search',knowledge_search, methods=['GET']),Route('/api/v1/projects/{project_id:str}/knowledge/apply',knowledge_apply, methods=['POST']),
      *interview_routes(factory=factory),
      
      *reevaluation_routes(factory=factory, evaluation_policy_revision=evaluation_policy_revision),
      
      
      
      Route('/api/v1/candidates/{candidate_id:str}/action-plan',candidate_action_plan,methods=['GET','PATCH']),Route('/api/v1/candidates/{candidate_id:str}/phone-script',candidate_phone_script,methods=['GET']),
      
      *reporting_routes(factory=factory, evaluation_policy_revision=evaluation_policy_revision),
      *system_routes(factory=factory, data_dir=data_dir, knowledge_dir=knowledge_dir, database_path=database_path, frontend_dist=frontend_dist),
    ]
    app.routes.extend(routes)
