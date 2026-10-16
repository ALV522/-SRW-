from __future__ import annotations
import hashlib, json, re
from sqlalchemy import select
from sqlalchemy.orm import Session
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.intake.service import CandidateIntakeService
from .models import FeedbackRecord

PREFIX_PATTERN=re.compile(r'^\s*([^：:]{1,20})[：:]\s*(.*)$')
CANDIDATE_PREFIXES={'候选人','候选人事实','事实','候选人反馈','candidate','candidate fact'}
JOB_PREFIXES={'岗位','岗位需求','需求','用人需求','job','requirement'}
CONFLICT_PREFIXES={'冲突','信息冲突','矛盾','conflict'}

def classify_feedback(text: str) -> dict:
    candidate_facts=[]; job_requirements=[]; conflicts=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line: continue
        m=PREFIX_PATTERN.match(line)
        if m:
            prefix,content=m.groups(); p=prefix.strip().lower(); content=content.strip()
            if prefix in CANDIDATE_PREFIXES or p in CANDIDATE_PREFIXES: candidate_facts.append(content); continue
            if prefix in JOB_PREFIXES or p in JOB_PREFIXES: job_requirements.append(content); continue
            if prefix in CONFLICT_PREFIXES or p in CONFLICT_PREFIXES: conflicts.append(content); continue
        candidate_facts.append(line)
    if job_requirements and (candidate_facts or conflicts): kind='mixed'
    elif job_requirements: kind='job_requirements'
    elif conflicts and not candidate_facts: kind='candidate_facts'
    else: kind='candidate_facts'
    questions=[]
    for item in conflicts[:3]: questions.append({'audience':'candidate','reason':'conflict','question':f'关于“{item}”存在信息冲突。请明确哪一项为准，并给出时间、范围或可核验依据。'})
    for item in candidate_facts[:3]: questions.append({'audience':'candidate','reason':'fact_verification','question':f'请补充“{item}”对应的时间、本人角色、范围以及一项可核验依据。'})
    for item in job_requirements[:3]: questions.append({'audience':'hiring_manager','reason':'protocol_review','question':f'新增岗位需求“{item}”应属于硬性条件、加分项还是仅作背景信息？是否需要进入正式评价标准？'})
    return {'feedback_type':kind,'candidate_facts':candidate_facts,'job_requirements':job_requirements,'conflicts':conflicts,'follow_up_questions':questions}

def _hash(text:str)->str: return hashlib.sha256(text.encode('utf-8')).hexdigest()

def create_feedback(session:Session, *, project_id:str, candidate_id:str|None, text:str, source_type:str='manual', actor:str='human')->FeedbackRecord:
    text=text.strip()
    if not text: raise V1InvariantError('feedback text is required')
    if candidate_id:
        c=session.get(Candidate,candidate_id)
        if not c or c.project_id!=project_id: raise V1NotFoundError('candidate not found in project')
    row=FeedbackRecord(project_id=project_id,candidate_id=candidate_id,source_type=source_type,raw_text=text,classification_json=json.dumps(classify_feedback(text),ensure_ascii=False,separators=(',',':')),content_hash=_hash(text),created_by=actor)
    session.add(row); session.flush()
    append_audit_event(session,event_type='feedback.created',entity_type='feedback_record',entity_id=row.id,project_id=project_id,candidate_id=candidate_id,actor=actor,payload={'source_type':source_type,'content_hash':row.content_hash})
    return row

def review_feedback(session:Session, feedback_id:str, *, action:str, reviewer:str, reason:str='', evaluation_policy_revision:str='policy.v1')->FeedbackRecord:
    row=session.get(FeedbackRecord,feedback_id)
    if not row: raise V1NotFoundError('feedback record not found')
    if row.status not in {'draft','reviewed'}: raise V1InvariantError(f'feedback is already {row.status}')
    if action not in {'review','apply_candidate_facts','reject'}: raise V1InvariantError('invalid feedback action')
    classified=json.loads(row.classification_json or '{}')
    if action=='reject': row.status='rejected'
    elif action=='review': row.status='reviewed'
    else:
        if not row.candidate_id: raise V1InvariantError('candidate feedback requires candidate_id')
        facts=[str(x).strip() for x in classified.get('candidate_facts',[]) if str(x).strip()]
        conflicts=[str(x).strip() for x in classified.get('conflicts',[]) if str(x).strip()]
        if not facts and not conflicts: raise V1InvariantError('no candidate facts to apply')
        text='\n'.join([*(f'候选人事实：{x}' for x in facts),*(f'冲突：{x}' for x in conflicts)])
        source=CandidateIntakeService(session).add_text_source(row.candidate_id,text,filename=f'feedback-{row.id}.txt',source_kind='feedback',media_type='text/plain')
        current_ids=get_current_source_ids(session,row.candidate_id)
        if source.id not in current_ids: current_ids=[*current_ids,source.id]
        material=MaterialRepository(session).publish_revision(row.candidate_id,current_ids,provenance={'action':'feedback_apply','feedback_record_id':row.id,'reviewer':reviewer})
        row.applied_source_id=source.id; row.applied_material_revision_id=material.id; row.status='applied'
    row.reviewed_by=reviewer; row.review_reason=reason; row.reviewed_at=utc_now()
    append_audit_event(session,event_type=f'feedback.{row.status}',entity_type='feedback_record',entity_id=row.id,project_id=row.project_id,candidate_id=row.candidate_id,actor=reviewer,reason=reason,payload={'feedback_type':classified.get('feedback_type'),'applied_material_revision_id':row.applied_material_revision_id})
    session.flush(); return row

def serialize_feedback(row:FeedbackRecord)->dict:
    try: classification=json.loads(row.classification_json or '{}')
    except Exception: classification={}
    return {'id':row.id,'project_id':row.project_id,'candidate_id':row.candidate_id,'source_type':row.source_type,'status':row.status,'classification':classification,'content_hash':row.content_hash,'created_by':row.created_by,'reviewed_by':row.reviewed_by,'review_reason':row.review_reason,'applied_source_id':row.applied_source_id,'applied_material_revision_id':row.applied_material_revision_id,'created_at':row.created_at.isoformat() if row.created_at else None,'reviewed_at':row.reviewed_at.isoformat() if row.reviewed_at else None}

def list_feedback(session:Session,project_id:str)->list[dict]:
    return [serialize_feedback(x) for x in session.scalars(select(FeedbackRecord).where(FeedbackRecord.project_id==project_id).order_by(FeedbackRecord.created_at.desc(),FeedbackRecord.id.desc()))]
