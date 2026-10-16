from __future__ import annotations
import sqlite3
from pathlib import Path
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import Session
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.protocol.models import Project
from srw.modules.planning.models import RecruitmentPlan
from .models import SourcingChannelObservation

COUNT_FIELDS=('sourced','contacted','screened','interviewed','offered','hired')

def record_observation(session:Session, project_id:str, *, channel:str, period:str, sourced:int, contacted:int, screened:int, interviewed:int, offered:int, hired:int, spend_cny:float, human_confirmed:bool, provenance:str, notes:str)->SourcingChannelObservation:
    if not session.get(Project,project_id): raise V1NotFoundError('project not found')
    channel=channel.strip()
    if not channel: raise V1InvariantError('channel is required')
    vals=[sourced,contacted,screened,interviewed,offered,hired]
    if any(isinstance(v,bool) or int(v)<0 for v in vals): raise V1InvariantError('channel counts must be non-negative integers')
    if not (sourced>=contacted>=screened>=interviewed>=offered>=hired):
        raise V1InvariantError('channel funnel must satisfy sourced >= contacted >= screened >= interviewed >= offered >= hired')
    if spend_cny < 0: raise V1InvariantError('spend_cny must be non-negative')
    row=SourcingChannelObservation(project_id=project_id,channel=channel,period=period.strip(),sourced=sourced,contacted=contacted,screened=screened,interviewed=interviewed,offered=offered,hired=hired,spend_cny=float(spend_cny),human_confirmed=bool(human_confirmed),provenance=(provenance.strip() or 'manual'),notes=notes.strip())
    session.add(row);session.flush();return row

def _ratio(n,d): return round(n/d,4) if d else None

def _channel_summary(rows:list[SourcingChannelObservation])->list[dict]:
    agg=defaultdict(lambda:{'sourced':0,'contacted':0,'screened':0,'interviewed':0,'offered':0,'hired':0,'spend_cny':0.0,'confirmed_observations':0,'observations':0})
    for r in rows:
        a=agg[r.channel];a['observations']+=1;a['confirmed_observations']+=int(bool(r.human_confirmed));a['spend_cny']+=float(r.spend_cny or 0)
        for f in COUNT_FIELDS:a[f]+=int(getattr(r,f) or 0)
    out=[]
    for channel,a in agg.items():
        confirmed=a['confirmed_observations']==a['observations'] and a['observations']>0
        out.append({'channel':channel,**a,'all_human_confirmed':confirmed,'contact_rate':_ratio(a['contacted'],a['sourced']),'screen_rate':_ratio(a['screened'],a['contacted']),'interview_rate':_ratio(a['interviewed'],a['screened']),'offer_rate':_ratio(a['offered'],a['interviewed']),'hire_rate_from_sourced':_ratio(a['hired'],a['sourced']),'cost_per_hire_cny':round(a['spend_cny']/a['hired'],2) if a['hired'] else None})
    # Descriptive ordering only: confirmed evidence, then hires, then sourced. It is NOT a candidate/hiring rank.
    out.sort(key=lambda x:(not x['all_human_confirmed'],-x['hired'],-x['sourced'],x['channel']))
    return out

def _market_signals(knowledge_dir:Path, role_title:str, location:str)->dict:
    p=Path(knowledge_dir)/'market_reference'/'knowledge.db'
    if not p.is_file(): return {'available':False,'signals':[],'guardrail':'market reference unavailable'}
    signals=[];q=role_title.strip();loc=location.strip()
    try:
        con=sqlite3.connect(str(p));con.row_factory=sqlite3.Row
        if q:
            rows=con.execute("SELECT job_title,salary_median_10k,shortage_level,regions,guardrail FROM beijing_skill_shortage WHERE job_title LIKE ? OR occupation_description LIKE ? LIMIT 8",(f'%{q}%',f'%{q}%')).fetchall()
            for r in rows: signals.append({'kind':'skill_shortage_reference','title':r['job_title'],'salary_median_10k':r['salary_median_10k'],'shortage_level':r['shortage_level'],'regions':r['regions'],'guardrail':r['guardrail']})
        wage_sql="SELECT period,geography,industry,occupation_group,annual_wage_cny,metric_scope,note FROM wage_benchmark"
        args=[];where=[]
        if loc: where.append('geography LIKE ?');args.append(f'%{loc}%')
        if q: where.append('(occupation_group LIKE ? OR industry LIKE ?)');args.extend([f'%{q}%',f'%{q}%'])
        if where:
            rows=con.execute(wage_sql+' WHERE '+' AND '.join(where)+' LIMIT 8',args).fetchall()
            for r in rows: signals.append({'kind':'wage_reference',**dict(r)})
        con.close()
    except sqlite3.Error as exc:
        return {'available':False,'signals':[],'guardrail':f'market reference read failed: {exc}'}
    return {'available':True,'signals':signals,'guardrail':'市场参考仅用于招聘计划与渠道判断，不直接转化为候选人分数或录用结论。'}

def intelligence_snapshot(session:Session, project_id:str, *, knowledge_dir:Path, role_title:str='', location:str='')->dict:
    project=session.get(Project,project_id)
    if not project: raise V1NotFoundError('project not found')
    plan=session.scalar(select(RecruitmentPlan).where(RecruitmentPlan.project_id==project_id))
    rows=list(session.scalars(select(SourcingChannelObservation).where(SourcingChannelObservation.project_id==project_id).order_by(SourcingChannelObservation.created_at.desc())))
    channels=_channel_summary(rows)
    configured=[]
    if plan:
        import json
        try:configured=json.loads(plan.source_channels_json or '[]')
        except Exception:configured=[]
    measured={x['channel'] for x in channels}
    blind=[x for x in configured if x not in measured]
    flags=[]
    if blind:flags.append({'code':'CHANNEL_MEASUREMENT_GAP','severity':'medium','text':'已配置渠道缺少效果观测：'+ '、'.join(blind)})
    if channels and any(not x['all_human_confirmed'] for x in channels):flags.append({'code':'UNCONFIRMED_CHANNEL_DATA','severity':'medium','text':'部分渠道数据尚未人工确认；不应据此自动调整招聘预算。'})
    return {'project_id':project_id,'channels':channels,'configured_channels':configured,'measurement_gaps':blind,'planning_flags':flags,'market':_market_signals(Path(knowledge_dir),role_title,location),'semantics':{'channel_efficiency_is_not_candidate_rank':True,'market_signal_is_not_candidate_score':True,'unconfirmed_observation_is_advisory_only':True}}
