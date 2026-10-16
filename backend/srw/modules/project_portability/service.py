from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from srw.kernel.ids import new_id
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.repository import append_audit_event
from srw.runtime.db.base import V1Base
from srw.runtime.db.models_registry import import_v1_models
from srw.runtime.db.schema import V1_SCHEMA_REVISION
from srw.release import get_release_state

FORMAT = 'srw-project-package'
SCHEMA_VERSION = 1
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 768 * 1024 * 1024
MAX_METADATA_BYTES = 96 * 1024 * 1024
CHUNK = 1024 * 1024

# Project-scoped business tables. Global runtime settings, templates and secrets are deliberately excluded.
TABLES = (
    'project','protocol_revision','candidate','candidate_contact','source','material_revision','material_source_binding',
    'claim','criterion_judgment','criterion_judgment_evidence','human_decision','shortlist_publication',
    'candidate_identity_review','criterion_anchor_case','judgment_review_item','candidate_stage_transition','offer_record',
    'candidate_action_plan','recruitment_event','interview_scorecard_submission','feedback_record','decision_action',
    'knowledge_feedback_draft','recruitment_plan','knowledge_curation_proposal','sourcing_channel_observation','work_item',
    'reevaluation_draft','evaluation_snapshot','ai_run','audit_event','task_record','job',
)

# Self-references are inserted as NULL first and restored after all IDs exist.
DEFERRED_SELF_FKS = {
    ('candidate','merged_into_candidate_id'),
    ('claim','supersedes_claim_id'),
    ('criterion_judgment','carried_forward_from_judgment_id'),
    ('human_decision','reaffirmed_from_decision_id'),
}
POINTERS = {('project','current_protocol_revision_id'),('candidate','current_material_revision_id')}

class ProjectPackageError(V1InvariantError):
    pass


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_dict(row: Any) -> dict[str,Any]:
    return {k:_json_value(v) for k,v in dict(row).items()}


def _safe_member(name: str) -> bool:
    if not name or '\\' in name:
        return False
    p = PurePosixPath(name)
    return not p.is_absolute() and '..' not in p.parts and ':' not in p.parts[0]


def _tables():
    import_v1_models()
    return V1Base.metadata.tables


def _collect_rows(session: Session, project_id: str) -> tuple[dict[str,list[dict]], list[str]]:
    tables = _tables()
    project_t = tables['project']
    project_row = session.execute(select(project_t).where(project_t.c.id==project_id)).mappings().first()
    if project_row is None:
        raise V1NotFoundError(f'project not found: {project_id}')
    candidate_t=tables['candidate']
    candidate_rows=list(session.execute(select(candidate_t).where(candidate_t.c.project_id==project_id)).mappings())
    candidate_ids=[str(x['id']) for x in candidate_rows]
    payload:dict[str,list[dict]]={'project':[_row_dict(project_row)],'candidate':[_row_dict(x) for x in candidate_rows]}

    for name in TABLES:
        if name in {'project','candidate','material_source_binding','criterion_judgment_evidence','job'}:
            continue
        t=tables[name]
        if 'project_id' in t.c:
            stmt=select(t).where(t.c.project_id==project_id)
        elif 'candidate_id' in t.c:
            if not candidate_ids:
                payload[name]=[];continue
            stmt=select(t).where(t.c.candidate_id.in_(candidate_ids))
        elif name=='task_record':
            # handled above through candidate_id branch; retained for readability
            stmt=select(t).where(t.c.candidate_id.in_(candidate_ids))
        else:
            payload[name]=[];continue
        payload[name]=[_row_dict(x) for x in session.execute(stmt).mappings()]

    material_ids=[str(x['id']) for x in payload.get('material_revision',[])]
    source_ids=[str(x['id']) for x in payload.get('source',[])]
    judgment_ids=[str(x['id']) for x in payload.get('criterion_judgment',[])]
    if material_ids and source_ids:
        t=tables['material_source_binding']
        payload['material_source_binding']=[_row_dict(x) for x in session.execute(select(t).where(t.c.material_revision_id.in_(material_ids),t.c.source_id.in_(source_ids))).mappings()]
    else: payload['material_source_binding']=[]
    claim_ids=[str(x['id']) for x in payload.get('claim',[])]
    if judgment_ids and claim_ids:
        t=tables['criterion_judgment_evidence']
        payload['criterion_judgment_evidence']=[_row_dict(x) for x in session.execute(select(t).where(t.c.judgment_id.in_(judgment_ids),t.c.claim_id.in_(claim_ids))).mappings()]
    else: payload['criterion_judgment_evidence']=[]

    # Include task rows whose payload is project-scoped even if they do not yet own a candidate (e.g. batch intake).
    task_t=tables['task_record']; existing={str(x['id']) for x in payload.get('task_record',[])}
    extra=session.execute(select(task_t).where(task_t.c.payload_json.like(f'%{project_id}%'))).mappings()
    for x in extra:
        if str(x['id']) not in existing:
            payload.setdefault('task_record',[]).append(_row_dict(x));existing.add(str(x['id']))
    job_ids=[str(x.get('job_id')) for x in payload.get('task_record',[]) if x.get('job_id')]
    if job_ids:
        jt=tables['job']; payload['job']=[_row_dict(x) for x in session.execute(select(jt).where(jt.c.id.in_(job_ids))).mappings()]
    else: payload['job']=[]
    for name in TABLES: payload.setdefault(name,[])
    return payload, source_ids


def export_project_package(session: Session, project_id: str, *, data_dir: Path, output_path: Path) -> dict[str,Any]:
    rows, _ = _collect_rows(session,project_id)
    project=rows['project'][0]
    package_payload={
        'format':FORMAT,'schema_version':SCHEMA_VERSION,'source_schema_revision':V1_SCHEMA_REVISION,
        'source_release':get_release_state()['version'],'exported_at':datetime.now(timezone.utc).isoformat(),
        'project':{'id':project['id'],'title':project['title']},'tables':rows,
        'import_semantics':{
            'ids_are_remapped_on_import':True,
            'decision_context_hashes_are_preserved_as_historical':True,
            'current_context_requires_reevaluation_after_import':True,
            'contains_personal_data':True,
        },
    }
    project_bytes=json.dumps(package_payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    blobs=[];seen=set();blob_root=Path(data_dir)/'blobs'
    for row in rows.get('source',[]):
        digest=str(row.get('blob_hash') or '').strip().lower()
        if not digest or digest in seen:continue
        if len(digest)!=64 or any(ch not in '0123456789abcdef' for ch in digest):
            raise ProjectPackageError(f'invalid source blob hash: {digest}')
        path=blob_root/digest[:2]/digest
        if not path.is_file():raise ProjectPackageError(f'source blob is missing: {digest}')
        actual=_sha_file(path)
        if actual!=digest:raise ProjectPackageError(f'source blob digest mismatch: {digest}')
        seen.add(digest);blobs.append({'sha256':digest,'path':f'blobs/{digest}','size':path.stat().st_size})
    manifest={
        'format':FORMAT,'schema_version':SCHEMA_VERSION,'project_id':project_id,'project_title':project['title'],
        'created_at':datetime.now(timezone.utc).isoformat(),'source_schema_revision':V1_SCHEMA_REVISION,
        'project_json_sha256':_sha_bytes(project_bytes),'blobs':blobs,
        'table_counts':{k:len(v) for k,v in rows.items()},
    }
    output_path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output_path,'w',zipfile.ZIP_DEFLATED,allowZip64=True) as z:
        z.writestr('project.json',project_bytes)
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        for item in blobs:
            digest=item['sha256'];z.write(blob_root/digest[:2]/digest,item['path'])
    if output_path.stat().st_size>MAX_PACKAGE_BYTES:
        output_path.unlink(missing_ok=True);raise ProjectPackageError('project package exceeds 512 MB limit')
    return manifest


def _read_limited(z:zipfile.ZipFile,info:zipfile.ZipInfo,limit:int)->bytes:
    if info.file_size>limit:raise ProjectPackageError(f'package member too large: {info.filename}')
    with z.open(info) as f:data=f.read(limit+1)
    if len(data)>limit:raise ProjectPackageError(f'package member too large: {info.filename}')
    return data


def _validate_to_staging(package_path:Path, staging:Path)->tuple[dict,dict,dict[str,Path]]:
    if not package_path.is_file() or package_path.stat().st_size>MAX_PACKAGE_BYTES:raise ProjectPackageError('project package missing or exceeds 512 MB')
    try:
        with zipfile.ZipFile(package_path) as z:
            infos=z.infolist();names=[x.filename for x in infos]
            if len(names)!=len(set(names)):raise ProjectPackageError('project package contains duplicate ZIP members')
            if not all(_safe_member(n) for n in names):raise ProjectPackageError('project package contains unsafe path')
            if any(x.file_size>MAX_MEMBER_BYTES for x in infos) or sum(x.file_size for x in infos)>MAX_EXPANDED_BYTES:raise ProjectPackageError('project package expanded size exceeds safety limit')
            by={x.filename:x for x in infos}
            if 'manifest.json' not in by or 'project.json' not in by:raise ProjectPackageError('project package missing manifest/project.json')
            manifest=json.loads(_read_limited(z,by['manifest.json'],MAX_METADATA_BYTES));raw=_read_limited(z,by['project.json'],MAX_METADATA_BYTES)
            if manifest.get('format')!=FORMAT or int(manifest.get('schema_version',0))!=SCHEMA_VERSION:raise ProjectPackageError('project package format/version unsupported')
            if manifest.get('source_schema_revision')!=V1_SCHEMA_REVISION:raise ProjectPackageError(f"project package schema {manifest.get('source_schema_revision')} is not compatible with {V1_SCHEMA_REVISION}")
            if _sha_bytes(raw)!=manifest.get('project_json_sha256'):raise ProjectPackageError('project.json digest mismatch')
            payload=json.loads(raw)
            if payload.get('format')!=FORMAT or payload.get('source_schema_revision')!=V1_SCHEMA_REVISION:raise ProjectPackageError('project payload schema mismatch')
            expected={'manifest.json','project.json'}; staged={};staging.mkdir(parents=True,exist_ok=True)
            for i,item in enumerate(manifest.get('blobs') or []):
                name=item.get('path');digest=str(item.get('sha256') or '')
                if not isinstance(name,str) or name not in by:raise ProjectPackageError('blob manifest references missing member')
                info=by[name]
                if int(item.get('size',-1))!=info.file_size:raise ProjectPackageError('blob size mismatch')
                target=staging/f'{i:06d}.blob';h=hashlib.sha256();written=0
                with z.open(info) as src,target.open('wb') as dst:
                    for chunk in iter(lambda:src.read(CHUNK),b''):
                        written+=len(chunk);h.update(chunk);dst.write(chunk)
                        if written>MAX_MEMBER_BYTES:raise ProjectPackageError('blob exceeds member limit')
                if h.hexdigest()!=digest:raise ProjectPackageError('blob digest mismatch')
                expected.add(name);staged[digest]=target
            if set(names)!=expected:raise ProjectPackageError('project package contains undeclared files')
            source_hashes={str(x.get('blob_hash') or '') for x in (payload.get('tables',{}).get('source') or []) if x.get('blob_hash')}
            if source_hashes!=set(staged):raise ProjectPackageError('source blob references do not match package blob manifest')
            return manifest,payload,staged
    except ProjectPackageError:raise
    except (zipfile.BadZipFile,json.JSONDecodeError,KeyError,ValueError,OSError) as exc:raise ProjectPackageError(f'project package is damaged: {exc}') from exc


def inspect_project_package(package_path:Path)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix='srw-project-package-inspect-') as td:
        manifest,payload,_=_validate_to_staging(Path(package_path),Path(td))
        return {
            'valid':True,'sha256':_sha_file(Path(package_path)),'project_title':manifest.get('project_title',''),
            'source_schema_revision':manifest.get('source_schema_revision',''),'table_counts':manifest.get('table_counts',{}),
            'blob_count':len(manifest.get('blobs') or []),'contains_personal_data':True,
            'decision_context_import_policy':'historical_then_reevaluate',
        }


def _deep_remap(value:Any,id_map:dict[str,str])->Any:
    if isinstance(value,str):return id_map.get(value,value)
    if isinstance(value,list):return [_deep_remap(x,id_map) for x in value]
    if isinstance(value,dict):return {k:_deep_remap(v,id_map) for k,v in value.items()}
    return value


def _convert_value(column,value):
    if value is None:return None
    try:py=column.type.python_type
    except Exception:return value
    if py is datetime and isinstance(value,str):return datetime.fromisoformat(value)
    return value


def import_project_package(session:Session, package_path:Path, *, data_dir:Path, actor:str='human')->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix='srw-project-import-') as td:
        manifest,payload,staged=_validate_to_staging(Path(package_path),Path(td)/'blobs')
        rows=payload.get('tables')
        if not isinstance(rows,dict) or len(rows.get('project') or [])!=1:raise ProjectPackageError('project package has invalid project rows')
        tables=_tables()
        id_map:dict[str,str]={}
        for name in TABLES:
            t=tables[name]
            if 'id' in t.c:
                for row in rows.get(name,[]) or []:
                    old=str(row.get('id') or '')
                    if old:id_map[old]=new_id()
        old_project=rows['project'][0];old_project_id=str(old_project['id']);new_project_id=id_map[old_project_id]
        deferred:list[tuple[str,str,str,str]]=[]

        def transformed(name:str,row:dict)->dict:
            t=tables[name];out={}
            for col in t.columns:
                if col.name not in row:continue
                value=row[col.name]
                if col.name=='id' and isinstance(value,str) and value in id_map:value=id_map[value]
                elif (name,col.name) in POINTERS or (name,col.name) in DEFERRED_SELF_FKS:
                    if value:deferred.append((name,str(id_map.get(str(row.get('id')),row.get('id'))),col.name,str(value)))
                    value=None
                elif col.name.endswith('_id') and isinstance(value,str):value=id_map.get(value,value)
                elif col.name in {'entity_id','source_ref'} and isinstance(value,str):value=id_map.get(value,value)
                elif col.name.endswith('_json') and isinstance(value,str):
                    try:value=json.dumps(_deep_remap(json.loads(value),id_map),ensure_ascii=False,separators=(',',':'))
                    except Exception:pass
                out[col.name]=_convert_value(col,value)
            return out

        # Insert in FK-safe order. Historical decision-context hashes are intentionally not recomputed.
        order=(
            'project','protocol_revision','candidate','source','material_revision','material_source_binding','candidate_contact',
            'claim','criterion_judgment','criterion_judgment_evidence','human_decision','shortlist_publication',
            'candidate_identity_review','criterion_anchor_case','judgment_review_item','candidate_stage_transition','offer_record',
            'candidate_action_plan','recruitment_event','interview_scorecard_submission','feedback_record','decision_action',
            'knowledge_feedback_draft','recruitment_plan','knowledge_curation_proposal','sourcing_channel_observation','work_item',
            'reevaluation_draft','evaluation_snapshot','ai_run','audit_event','job','task_record',
        )
        for name in order:
            t=tables[name]
            for raw in rows.get(name,[]) or []:
                vals=transformed(name,raw)
                if name=='project':vals['title']=str(vals.get('title') or 'Imported project')+'（导入）'
                session.execute(t.insert().values(**vals))
        # Restore current pointers and self references after all referenced rows exist.
        for name,new_row_id,column,old_target in deferred:
            target=id_map.get(old_target)
            if target:
                session.execute(tables[name].update().where(tables[name].c.id==new_row_id).values({column:target}))
        # Copy immutable content-addressed blobs. Existing identical blob is reused.
        blob_root=Path(data_dir)/'blobs'
        for digest,source in staged.items():
            dest=blob_root/digest[:2]/digest;dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists():
                if _sha_file(dest)!=digest:raise ProjectPackageError(f'existing blob digest mismatch: {digest}')
            else:
                tmp=dest.with_suffix('.importing');shutil.copy2(source,tmp)
                if _sha_file(tmp)!=digest:tmp.unlink(missing_ok=True);raise ProjectPackageError(f'imported blob digest mismatch: {digest}')
                os.replace(tmp,dest)
        append_audit_event(session,event_type='PROJECT_PACKAGE_IMPORTED',entity_type='project',entity_id=new_project_id,project_id=new_project_id,actor=actor,reason='project portability import',payload={'source_project_id':old_project_id,'package_sha256':_sha_file(Path(package_path)),'decision_context_policy':'historical_then_reevaluate','source_release':payload.get('source_release')})
        return {
            'project_id':new_project_id,'title':str(old_project.get('title') or '')+'（导入）','source_project_id':old_project_id,
            'package_sha256':_sha_file(Path(package_path)),'table_counts':manifest.get('table_counts',{}),'blob_count':len(staged),
            'decision_context_policy':'historical_then_reevaluate','requires_current_context_reevaluation':True,
        }
