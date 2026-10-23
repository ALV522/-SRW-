from __future__ import annotations
import json
from pathlib import Path
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from srw.kernel.errors import V1InvariantError
from srw.modules.feedback.service import create_feedback,list_feedback,review_feedback
from srw.modules.decision_operations.models import DecisionAction,KnowledgeFeedbackDraft
from srw.modules.decision_operations.service import recommend_actions,transition_action,stage_knowledge_feedback,action_payload
from srw.modules.planning.service import upsert_plan,planning_snapshot
from srw.modules.knowledge_governance.models import KnowledgeCurationProposal
from srw.modules.knowledge_governance.service import create_from_feedback,review_proposal,export_proposal,payload as curation_payload

async def _json(request:Request)->dict:
    try:v=await request.json()
    except Exception as exc: raise V1InvariantError('request body must be valid JSON') from exc
    if not isinstance(v,dict): raise V1InvariantError('request body must be an object')
    return v

def _str(b,k,default=''):
    v=b.get(k,default)
    if v is None:return ''
    if not isinstance(v,str):raise V1InvariantError(f'{k} must be a string')
    return v.strip()

def _int(b,k,default=0):
    v=b.get(k,default)
    if isinstance(v,bool) or not isinstance(v,int):raise V1InvariantError(f'{k} must be an integer')
    return v

def _action_list(session,project_id):
    rows=session.scalars(select(DecisionAction).where(DecisionAction.project_id==project_id).order_by(DecisionAction.status,DecisionAction.priority.desc(),DecisionAction.created_at.desc())).all()
    return [action_payload(x) for x in rows]

def _knowledge_feedback(session,project_id):
    rows=session.scalars(select(KnowledgeFeedbackDraft).where(KnowledgeFeedbackDraft.project_id==project_id).order_by(KnowledgeFeedbackDraft.created_at.desc())).all()
    out=[]
    for x in rows:
        out.append({'id':x.id,'project_id':x.project_id,'candidate_id':x.candidate_id,'decision_action_id':x.decision_action_id,'status':x.status,'feedback_type':x.feedback_type,'title':x.title,'summary':x.summary,'evidence_refs':json.loads(x.evidence_refs_json or '[]'),'decision_context_hash':x.decision_context_hash,'reviewed_by':x.reviewed_by,'created_at':x.created_at.isoformat() if x.created_at else None})
    return out

def install_decision_operations_http_routes(app,factory,*,data_dir:Path,evaluation_policy_revision:str):
    export_root=Path(data_dir)/'knowledge_curation_exports'

    async def project_operations(request):
        pid=request.path_params['project_id']
        with factory() as s:
            return JSONResponse({'planning':planning_snapshot(s,pid,evaluation_policy_revision),'actions':_action_list(s,pid),'feedback':list_feedback(s,pid),'knowledge_feedback':_knowledge_feedback(s,pid),'curation':[curation_payload(x) for x in s.scalars(select(KnowledgeCurationProposal).where(KnowledgeCurationProposal.project_id==pid).order_by(KnowledgeCurationProposal.created_at.desc())).all()]})

    async def planning_get(request):
        with factory() as s:return JSONResponse(planning_snapshot(s,request.path_params['project_id'],evaluation_policy_revision))
    async def planning_put(request):
        b=await _json(request);channels=b.get('source_channels') or []
        if not isinstance(channels,list):raise V1InvariantError('source_channels must be an array')
        with factory.begin() as s:
            upsert_plan(s,request.path_params['project_id'],target_hires=_int(b,'target_hires',1),target_date=_str(b,'target_date'),owner=_str(b,'owner'),source_channels=channels,notes=_str(b,'notes'))
            return JSONResponse(planning_snapshot(s,request.path_params['project_id'],evaluation_policy_revision))

    async def actions_recommend(request):
        pid=request.path_params['project_id']
        with factory.begin() as s:
            rows=recommend_actions(s,pid,evaluation_policy_revision);return JSONResponse({'project_id':pid,'ranking_kind':'operational_priority','actions':[action_payload(x) for x in rows]})
    async def actions_list(request):
        with factory() as s:return JSONResponse({'actions':_action_list(s,request.path_params['project_id']),'ranking_kind':'operational_priority'})
    async def action_transition(request):
        b=await _json(request)
        with factory.begin() as s:
            x=transition_action(s,request.path_params['action_id'],transition=_str(b,'transition'),actor=_str(b,'actor','human') or 'human',expected_state_version=_int(b,'expected_state_version',0),outcome=b.get('outcome') if isinstance(b.get('outcome'),dict) else None,reason=_str(b,'reason'))
            return JSONResponse(action_payload(x))
    async def action_stage_feedback(request):
        b=await _json(request)
        with factory.begin() as s:
            x=stage_knowledge_feedback(s,request.path_params['action_id'],actor=_str(b,'actor','human') or 'human');return JSONResponse({'id':x.id,'status':x.status,'title':x.title,'summary':x.summary})

    async def feedback_list(request):
        with factory() as s:return JSONResponse({'feedback':list_feedback(s,request.path_params['project_id'])})
    async def feedback_create(request):
        b=await _json(request)
        with factory.begin() as s:
            x=create_feedback(s,project_id=request.path_params['project_id'],candidate_id=_str(b,'candidate_id') or None,text=_str(b,'text'),source_type=_str(b,'source_type','manual') or 'manual',actor=_str(b,'actor','human') or 'human');return JSONResponse({'id':x.id,'status':x.status,'classification':json.loads(x.classification_json or '{}')})
    async def feedback_review(request):
        b=await _json(request)
        with factory.begin() as s:
            x=review_feedback(s,request.path_params['feedback_id'],action=_str(b,'action'),reviewer=_str(b,'reviewer','human') or 'human',reason=_str(b,'reason'),evaluation_policy_revision=evaluation_policy_revision);return JSONResponse({'id':x.id,'status':x.status,'applied_source_id':x.applied_source_id,'applied_material_revision_id':x.applied_material_revision_id})

    async def knowledge_feedback_promote(request):
        b=await _json(request)
        with factory.begin() as s:
            p=create_from_feedback(s,request.path_params['feedback_id'],actor=_str(b,'actor','human') or 'human');return JSONResponse(curation_payload(p))
    async def curation_list(request):
        pid=request.path_params['project_id']
        with factory() as s:return JSONResponse({'proposals':[curation_payload(x) for x in s.scalars(select(KnowledgeCurationProposal).where(KnowledgeCurationProposal.project_id==pid).order_by(KnowledgeCurationProposal.created_at.desc())).all()],'active_knowledge_mutated':False})
    async def curation_review(request):
        b=await _json(request)
        with factory.begin() as s:
            p=review_proposal(s,request.path_params['proposal_id'],action=_str(b,'action'),reviewer=_str(b,'reviewer','human') or 'human',reason=_str(b,'reason'),expected_state_version=_int(b,'expected_state_version',0));return JSONResponse(curation_payload(p))
    async def curation_export(request):
        b=await _json(request)
        with factory.begin() as s:
            p,path=export_proposal(s,request.path_params['proposal_id'],actor=_str(b,'actor','human') or 'human',export_root=export_root);return JSONResponse({**curation_payload(p),'export_file':path.name,'active_knowledge_mutated':False})

    app.routes.extend([
      Route('/api/v1/projects/{project_id:str}/operations-learning',project_operations,methods=['GET']),
      Route('/api/v1/projects/{project_id:str}/planning',planning_get,methods=['GET']),Route('/api/v1/projects/{project_id:str}/planning',planning_put,methods=['PUT']),
      Route('/api/v1/projects/{project_id:str}/decision-actions',actions_list,methods=['GET']),Route('/api/v1/projects/{project_id:str}/decision-actions/recommend',actions_recommend,methods=['POST']),Route('/api/v1/decision-actions/{action_id:str}/transition',action_transition,methods=['POST']),Route('/api/v1/decision-actions/{action_id:str}/knowledge-feedback',action_stage_feedback,methods=['POST']),
      Route('/api/v1/projects/{project_id:str}/feedback',feedback_list,methods=['GET']),Route('/api/v1/projects/{project_id:str}/feedback',feedback_create,methods=['POST']),Route('/api/v1/feedback/{feedback_id:str}/review',feedback_review,methods=['POST']),
      Route('/api/v1/knowledge-feedback/{feedback_id:str}/promote',knowledge_feedback_promote,methods=['POST']),Route('/api/v1/projects/{project_id:str}/knowledge-curation',curation_list,methods=['GET']),Route('/api/v1/knowledge-curation/{proposal_id:str}/review',curation_review,methods=['POST']),Route('/api/v1/knowledge-curation/{proposal_id:str}/export',curation_export,methods=['POST']),
    ])
