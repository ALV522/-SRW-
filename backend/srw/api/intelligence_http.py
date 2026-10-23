from __future__ import annotations
import json
from pathlib import Path
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from srw.kernel.errors import V1InvariantError,V1NotFoundError
from srw.modules.protocol.models import Project,ProtocolRevision
from srw.modules.recruitment_intelligence.service import record_observation,intelligence_snapshot
from srw.modules.recruitment_intelligence.models import SourcingChannelObservation
from srw.modules.knowledge_governance.models import KnowledgeCurationProposal
from srw.modules.knowledge_packages.service import ControlledKnowledgePackages

async def _json(request:Request)->dict:
    try:v=await request.json()
    except Exception as exc:raise V1InvariantError('request body must be valid JSON') from exc
    if not isinstance(v,dict):raise V1InvariantError('request body must be an object')
    return v

def _str(b,k,d=''):
    v=b.get(k,d)
    if v is None:return ''
    if not isinstance(v,str):raise V1InvariantError(f'{k} must be a string')
    return v.strip()
def _int(b,k,d=0):
    v=b.get(k,d)
    if isinstance(v,bool) or not isinstance(v,int):raise V1InvariantError(f'{k} must be an integer')
    return v
def _num(b,k,d=0.0):
    v=b.get(k,d)
    if isinstance(v,bool) or not isinstance(v,(int,float)):raise V1InvariantError(f'{k} must be numeric')
    return float(v)

def _job_context(session,project_id):
    p=session.get(Project,project_id)
    if not p:raise V1NotFoundError('project not found')
    role=p.title;location=''
    if p.current_protocol_revision_id:
        r=session.get(ProtocolRevision,p.current_protocol_revision_id)
        if r:
            try:
                data=json.loads(r.payload_json or '{}');ctx=data.get('recruitment_context') or {};brief=data.get('brief') or {};role=str(ctx.get('role_title') or brief.get('title') or p.title);location=str(ctx.get('location') or '')
            except Exception:pass
    return role,location

def install_intelligence_http_routes(app,factory,*,data_dir:Path,knowledge_dir:Path):
    packages=ControlledKnowledgePackages(data_dir=Path(data_dir),active_dir=Path(knowledge_dir))
    async def intel(request):
        pid=request.path_params['project_id']
        with factory() as s:
            role,loc=_job_context(s,pid);return JSONResponse(intelligence_snapshot(s,pid,knowledge_dir=Path(knowledge_dir),role_title=role,location=loc))
    async def observation_create(request):
        b=await _json(request);pid=request.path_params['project_id']
        with factory.begin() as s:
            x=record_observation(s,pid,channel=_str(b,'channel'),period=_str(b,'period'),sourced=_int(b,'sourced'),contacted=_int(b,'contacted'),screened=_int(b,'screened'),interviewed=_int(b,'interviewed'),offered=_int(b,'offered'),hired=_int(b,'hired'),spend_cny=_num(b,'spend_cny'),human_confirmed=bool(b.get('human_confirmed') is True),provenance=_str(b,'provenance','manual') or 'manual',notes=_str(b,'notes'))
            return JSONResponse({'id':x.id,'channel':x.channel,'human_confirmed':x.human_confirmed})
    async def observation_list(request):
        pid=request.path_params['project_id']
        with factory() as s:
            rows=s.scalars(select(SourcingChannelObservation).where(SourcingChannelObservation.project_id==pid).order_by(SourcingChannelObservation.created_at.desc())).all();return JSONResponse({'observations':[{'id':x.id,'channel':x.channel,'period':x.period,'sourced':x.sourced,'contacted':x.contacted,'screened':x.screened,'interviewed':x.interviewed,'offered':x.offered,'hired':x.hired,'spend_cny':x.spend_cny,'human_confirmed':x.human_confirmed,'provenance':x.provenance,'notes':x.notes} for x in rows]})
    async def package_list(_request):return JSONResponse({'packages':packages.list_packages()})
    async def prepare_apply(request):
        b=await _json(request);pid=request.path_params['proposal_id']
        with factory() as s:
            p=s.get(KnowledgeCurationProposal,pid)
            if not p:raise V1NotFoundError('curation proposal not found')
            if p.status not in {'reviewed','exported'}:raise V1InvariantError('proposal must be human-reviewed before apply preparation')
            if p.proposed_action not in {'confirm_alias','confirm_specialization','confirm_competency_alias'}:raise V1InvariantError('this governance action is export-only; controlled apply supports title and competency aliases only')
            actor=p.reviewer or _str(b,'actor','human') or 'human';reason=p.review_reason or _str(b,'reason')
            if p.proposed_action=='confirm_competency_alias':
                manifest=packages.prepare_competency_alias(proposal_id=p.id,source_title=_str(b,'source_title'),target_id=_str(b,'target_id'),reviewer=actor,reason=reason)
            else:
                expected='specialization' if p.proposed_action=='confirm_specialization' else _str(b,'target_type','role')
                if expected not in {'role','specialization'}:raise V1InvariantError('invalid target type')
                manifest=packages.prepare_taxonomy_alias(proposal_id=p.id,source_title=_str(b,'source_title'),target_id=_str(b,'target_id'),target_type=expected,reviewer=actor,reason=reason)
            return JSONResponse(manifest)
    async def activate(request):
        b=await _json(request);return JSONResponse(packages.activate(request.path_params['package_id'],expected_digest=_str(b,'expected_digest'),actor=_str(b,'actor','human') or 'human'))
    async def rollback(request):
        b=await _json(request);return JSONResponse(packages.rollback(actor=_str(b,'actor','human') or 'human'))
    app.routes.extend([
      Route('/api/v1/projects/{project_id:str}/recruitment-intelligence',intel,methods=['GET']),
      Route('/api/v1/projects/{project_id:str}/sourcing-observations',observation_list,methods=['GET']),Route('/api/v1/projects/{project_id:str}/sourcing-observations',observation_create,methods=['POST']),
      Route('/api/v1/knowledge-packages',package_list,methods=['GET']),Route('/api/v1/knowledge-curation/{proposal_id:str}/prepare-apply',prepare_apply,methods=['POST']),Route('/api/v1/knowledge-packages/{package_id:str}/activate',activate,methods=['POST']),Route('/api/v1/knowledge-packages/rollback',rollback,methods=['POST']),
    ])
