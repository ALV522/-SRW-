from __future__ import annotations
import hashlib,json,os,shutil,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
from typing import Any
from srw.kernel.errors import V1InvariantError,V1NotFoundError

ALLOWED_SOURCES={'taxonomy','job_info','competency','market_reference','reference'}
REQUIRED_TABLES={
 'taxonomy':{'schema_meta','canonical_role','title_alias','title_mapping'},
 'job_info':{'schema_meta','profile','profile_item'},
 'competency':{'schema_meta','competency','competency_facet','job_competency_requirement','evidence_policy'},
 'market_reference':{'schema_meta','source_record','wage_benchmark','local_supply_demand','role_market_mapping'},
 'reference':{'schema_meta','source_registry','reference_entity','reference_job_profile','quality_metric'},
}
SEMANTIC_TABLES={'taxonomy':{'canonical_role':'role_id','specialization':'specialization_id','title_alias':'alias_id','title_mapping':'mapping_id'},'competency':{'competency':'competency_id','competency_alias':'alias_id'}}

def _sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def _db_check(path:Path,source_type:str)->dict[str,Any]:
 try:
  with closing(sqlite3.connect(path)) as con:
   integrity=con.execute('PRAGMA integrity_check').fetchone()[0];fk=list(con.execute('PRAGMA foreign_key_check'));tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")};missing=sorted(REQUIRED_TABLES[source_type]-tables)
 except sqlite3.Error as exc:raise V1InvariantError(f'{source_type} SQLite unreadable: {exc}') from exc
 if integrity!='ok':raise V1InvariantError(f'{source_type} integrity_check failed: {integrity}')
 if fk:raise V1InvariantError(f'{source_type} has foreign-key violations: {len(fk)}')
 if missing:raise V1InvariantError(f'{source_type} missing required tables: {missing}')
 return {'integrity':'ok','foreign_key_violations':0,'table_count':len(tables),'sha256':_sha(path)}

def _semantic_rows(path:Path,table:str,keycol:str)->dict[str,str]:
 con=sqlite3.connect(path);con.row_factory=sqlite3.Row
 try:
  tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if table not in tables:return {}
  out={}
  for row in con.execute(f'SELECT rowid AS __rowid__,* FROM "{table}" ORDER BY rowid'):
   d=dict(row);key=str(d.get(keycol,'')).strip()
   if not key:continue
   semantic={k:v for k,v in d.items() if k not in {'__rowid__','created_at','updated_at','retrieved_at'}}
   out[key]=str(d.get('content_hash') or hashlib.sha256(json.dumps(semantic,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest())
  return out
 finally:con.close()

def semantic_diff(old_path:Path,new_path:Path,source_type:str)->dict[str,Any]:
 tables=[];tot={'added':0,'removed':0,'changed':0}
 for table,key in SEMANTIC_TABLES.get(source_type,{}).items():
  old=_semantic_rows(old_path,table,key);new=_semantic_rows(new_path,table,key);added=sorted(set(new)-set(old));removed=sorted(set(old)-set(new));changed=sorted(k for k in set(old)&set(new) if old[k]!=new[k]);tot['added']+=len(added);tot['removed']+=len(removed);tot['changed']+=len(changed);tables.append({'table':table,'added':len(added),'removed':len(removed),'changed':len(changed),'examples':{'added':added[:8],'removed':removed[:8],'changed':changed[:8]}})
 return {'source_type':source_type,**tot,'tables':tables}

class ControlledKnowledgePackages:
 def __init__(self,*,data_dir:Path,active_dir:Path):
  self.data_dir=Path(data_dir);self.active_dir=Path(active_dir);self.root=self.data_dir/'knowledge_governance';self.packages=self.root/'packages';self.backups=self.root/'activation_backups';self.state=self.root/'active_state.json'
 def _state(self):
  if not self.state.is_file():return {'history':[]}
  try:return json.loads(self.state.read_text(encoding='utf-8'))
  except Exception:return {'history':[]}
 def list_packages(self):
  out=[]
  if self.packages.is_dir():
   for p in sorted(self.packages.iterdir(),reverse=True):
    mf=p/'manifest.json'
    if mf.is_file():
     try:out.append(json.loads(mf.read_text(encoding='utf-8')))
     except Exception:pass
  return out
 def prepare_taxonomy_alias(self,*,proposal_id:str,source_title:str,target_id:str,target_type:str,reviewer:str,reason:str)->dict:
  if target_type not in {'role','specialization'}:raise V1InvariantError('target_type must be role or specialization')
  source_title=source_title.strip();target_id=target_id.strip()
  if not source_title or not target_id:raise V1InvariantError('source_title and target_id are required')
  source=self.active_dir/'taxonomy'/'knowledge.db'
  if not source.is_file():raise V1NotFoundError('taxonomy knowledge database not found')
  package_id='curation-'+proposal_id
  folder=self.packages/package_id
  if folder.exists():raise V1InvariantError('prepared package already exists for proposal')
  folder.mkdir(parents=True,exist_ok=False);new=folder/'taxonomy.db';shutil.copy2(source,new)
  con=sqlite3.connect(new)
  try:
   target_table='canonical_role' if target_type=='role' else 'specialization';target_key='role_id' if target_type=='role' else 'specialization_id'
   if con.execute(f'SELECT 1 FROM {target_table} WHERE {target_key}=?',(target_id,)).fetchone() is None:raise V1InvariantError('curation target does not exist in active taxonomy')
   normalized=' '.join(source_title.lower().split())
   existing=con.execute('SELECT alias_id FROM title_alias WHERE normalized_title=? AND status=?',(normalized,'active')).fetchone()
   if existing:alias_id=str(existing[0])
   else:
    alias_id='CUR-'+hashlib.sha256((proposal_id+'|'+normalized).encode()).hexdigest()[:16].upper()
    con.execute('INSERT INTO title_alias(alias_id,title,normalized_title,language,alias_type,ambiguity,source_id,status) VALUES (?,?,?,?,?,?,?,?)',(alias_id,source_title,normalized,'zh' if any(ord(c)>127 for c in source_title) else 'en','curated_feedback',0,None,'active'))
   mapping_id='CURMAP-'+hashlib.sha256((proposal_id+'|'+alias_id+'|'+target_id).encode()).hexdigest()[:16].upper()
   current=con.execute('SELECT target_type,target_id FROM title_mapping WHERE alias_id=? AND status=?',(alias_id,'active')).fetchall()
   if any(str(r[0])!=target_type or str(r[1])!=target_id for r in current):raise V1InvariantError('alias already has an active mapping to a different target; manual conflict resolution required')
   if not any(str(r[0])==target_type and str(r[1])==target_id for r in current):
    con.execute('INSERT INTO title_mapping(mapping_id,alias_id,target_type,target_id,mapping_type,seniority_hint,management_scope_hint,confidence,rationale,status,valid_from,valid_to,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(mapping_id,alias_id,target_type,target_id,'curated_feedback',None,None,1.0,f'Human-governed curation by {reviewer}: {reason}'[:1000],'active','2026-10-16',None,'srw-v1-curation'))
   con.commit()
  finally:con.close()
  check=_db_check(new,'taxonomy');diff=semantic_diff(source,new,'taxonomy');digest=_sha(new)
  manifest={'schema':'srw.controlled-knowledge-package.v1','package_id':package_id,'proposal_id':proposal_id,'status':'prepared','sources':[{'source_type':'taxonomy','file':'taxonomy.db','sha256':digest,'check':check}],'semantic_diff':{'sources':[diff],'totals':{'added':diff['added'],'removed':diff['removed'],'changed':diff['changed']}},'reviewer':reviewer,'review_reason':reason,'activation_requires_explicit_digest':digest,'active_knowledge_mutated':False}
  (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');return manifest
 def prepare_competency_alias(self,*,proposal_id:str,source_title:str,target_id:str,reviewer:str,reason:str)->dict:
  source_title=source_title.strip();target_id=target_id.strip()
  if not source_title or not target_id:raise V1InvariantError('source_title and target_id are required')
  source=self.active_dir/'competency'/'knowledge.db'
  if not source.is_file():raise V1NotFoundError('competency knowledge database not found')
  package_id='curation-'+proposal_id
  folder=self.packages/package_id
  if folder.exists():raise V1InvariantError('prepared package already exists for proposal')
  folder.mkdir(parents=True,exist_ok=False);new=folder/'competency.db';shutil.copy2(source,new)
  con=sqlite3.connect(new)
  try:
   if con.execute('SELECT 1 FROM competency WHERE competency_id=? AND status=?',(target_id,'active')).fetchone() is None:raise V1InvariantError('curation target competency does not exist or is inactive')
   existing=con.execute('SELECT alias_id,competency_id FROM competency_alias WHERE trim(alias)=trim(?) COLLATE NOCASE AND status=?',(source_title,'active')).fetchall()
   if any(str(r[1])!=target_id for r in existing):raise V1InvariantError('competency alias already points to a different active competency; manual conflict resolution required')
   if not any(str(r[1])==target_id for r in existing):
    alias_id='CURCA-'+hashlib.sha256((proposal_id+'|'+source_title.casefold()+'|'+target_id).encode()).hexdigest()[:16].upper()
    con.execute('INSERT INTO competency_alias(alias_id,competency_id,alias,language,alias_type,source_id,status) VALUES (?,?,?,?,?,?,?)',(alias_id,target_id,source_title,'zh' if any(ord(c)>127 for c in source_title) else 'en','curated_feedback',None,'active'))
   con.commit()
  finally:con.close()
  check=_db_check(new,'competency');diff=semantic_diff(source,new,'competency');digest=_sha(new)
  manifest={'schema':'srw.controlled-knowledge-package.v1','package_id':package_id,'proposal_id':proposal_id,'status':'prepared','sources':[{'source_type':'competency','file':'competency.db','sha256':digest,'check':check}],'semantic_diff':{'sources':[diff],'totals':{'added':diff['added'],'removed':diff['removed'],'changed':diff['changed']}},'reviewer':reviewer,'review_reason':reason,'activation_requires_explicit_digest':digest,'active_knowledge_mutated':False}
  (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');return manifest
 def activate(self,package_id:str,*,expected_digest:str,actor:str)->dict:
  folder=self.packages/package_id;mf=folder/'manifest.json'
  if not mf.is_file():raise V1NotFoundError('prepared knowledge package not found')
  manifest=json.loads(mf.read_text(encoding='utf-8'))
  if manifest.get('status') not in {'prepared','rolled_back'}:raise V1InvariantError('package is not activatable')
  srcinfo=manifest['sources'][0];src=folder/srcinfo['file'];actual=_sha(src)
  if expected_digest.strip().lower()!=actual:raise V1InvariantError('activation digest mismatch; refresh semantic diff before applying')
  _db_check(src,srcinfo['source_type']);dest=self.active_dir/srcinfo['source_type']/'knowledge.db';_db_check(dest,srcinfo['source_type'])
  self.backups.mkdir(parents=True,exist_ok=True);backup=self.backups/f'{package_id}-{_sha(dest)[:12]}.db';shutil.copy2(dest,backup);_db_check(backup,srcinfo['source_type'])
  tmp=dest.with_suffix('.curation.new');shutil.copy2(src,tmp);_db_check(tmp,srcinfo['source_type'])
  try:os.replace(tmp,dest)
  except Exception:
   tmp.unlink(missing_ok=True);raise
  st=self._state();history=list(st.get('history',[]));history.append({'package_id':package_id,'source_type':srcinfo['source_type'],'backup':str(backup),'activated_by':actor,'activated_sha256':_sha(dest)});self.root.mkdir(parents=True,exist_ok=True);tmpstate=self.state.with_suffix('.tmp');tmpstate.write_text(json.dumps({'history':history[-50:]},ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmpstate,self.state)
  manifest['status']='active';manifest['activated_by']=actor;manifest['active_knowledge_mutated']=True;mf.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
  return {'status':'active','package_id':package_id,'source_type':srcinfo['source_type'],'sha256':_sha(dest),'rollback_available':True,'semantic_diff':manifest['semantic_diff']}
 def rollback(self,*,actor:str)->dict:
  st=self._state();history=list(st.get('history',[]))
  if not history:raise V1InvariantError('no knowledge activation history to roll back')
  last=history[-1];backup=Path(last['backup']);source_type=last['source_type'];dest=self.active_dir/source_type/'knowledge.db'
  if not backup.is_file():raise V1InvariantError('rollback backup is missing')
  _db_check(backup,source_type);tmp=dest.with_suffix('.rollback.new');shutil.copy2(backup,tmp);_db_check(tmp,source_type);os.replace(tmp,dest)
  package_id=last['package_id'];mf=self.packages/package_id/'manifest.json'
  if mf.is_file():
   m=json.loads(mf.read_text(encoding='utf-8'));m['status']='rolled_back';m['rolled_back_by']=actor;m['active_knowledge_mutated']=False;mf.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
  tmpstate=self.state.with_suffix('.tmp');tmpstate.write_text(json.dumps({'history':history[:-1]},ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmpstate,self.state)
  return {'status':'rolled_back','package_id':package_id,'source_type':source_type,'sha256':_sha(dest),'active_knowledge_mutated':True}
