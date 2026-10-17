from __future__ import annotations

import base64, hashlib, json, os, shutil, sqlite3, tempfile, zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base
from srw.runtime.backup_truth import write_backup_archive


class RoleTemplate(V1Base):
    __tablename__ = "role_template"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class TaskRecord(V1Base):
    __tablename__ = "task_record"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class RecruitmentEvent(V1Base):
    __tablename__ = "recruitment_event"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interviewer: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    location: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    event_state: Mapped[str] = mapped_column(String(24), nullable=False, default="completed", index=True)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ReevaluationDraft(V1Base):
    __tablename__ = "reevaluation_draft"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposal_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    protocol_revision_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    material_revision_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    decision_context_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    diff_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationSnapshot(V1Base):
    __tablename__ = "evaluation_snapshot"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_context_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reevaluation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    snapshot_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BlobStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
    def put(self, raw: bytes) -> str:
        digest=hashlib.sha256(raw).hexdigest()
        p=self.root/digest[:2]/digest
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists(): p.write_bytes(raw)
        return digest
    def get(self, digest: str) -> bytes:
        return (self.root/digest[:2]/digest).read_bytes()


class KnowledgeService:
    DB_NAMES=("taxonomy","job_info","competency","market_reference","reference")
    def __init__(self, root: Path): self.root=Path(root)
    def status(self) -> list[dict[str,Any]]:
        out=[]
        for name in self.DB_NAMES:
            p=self.root/name/"knowledge.db"
            out.append({"name":name,"available":p.is_file(),"size_bytes":p.stat().st_size if p.is_file() else 0})
        return out
    def search(self, query: str, limit: int=10) -> list[dict[str,Any]]:
        q=query.strip()
        if not q: return []
        specs={
          "taxonomy":("alias_fts",["alias_id","title"]),
          "job_info":("profile_fts",["item_version_id","profile_id","item_type","item_text","evidence_hint"]),
          "competency":("competency_fts",["competency_id","name_zh","name_en","definition","facet_text"]),
          "reference":("reference_entity_fts",["entity_id","title","normalized_title","level1","level2","level3"]),
          "market_reference":("beijing_core_field",["field_id","industry","core_field","representative_positions","core_competency_requirements"]),
        }
        per_db={}
        for name,(table,cols) in specs.items():
            p=self.root/name/"knowledge.db"
            if not p.is_file(): continue
            values=[]
            try:
                con=sqlite3.connect(str(p)); con.row_factory=sqlite3.Row
                where=" OR ".join([f'CAST("{c}" AS TEXT) LIKE ?' for c in cols])
                sql=f'SELECT {",".join([chr(34)+c+chr(34) for c in cols])} FROM "{table}" WHERE {where} LIMIT ?'
                rows=con.execute(sql,[f"%{q}%"]*len(cols)+[max(10,limit*3)]).fetchall();con.close()
                for r in rows:
                    fields={c:r[c] for c in cols}
                    title=str(fields.get("title") or fields.get("name_zh") or fields.get("core_field") or fields.get("item_text") or fields.get(cols[0]) or "")
                    detail=" · ".join(str(v) for v in fields.values() if v not in (None,"") and str(v)!=title)[:800]
                    hay=(title+" "+detail).lower();needle=q.lower()
                    score=100 if title.lower()==needle else (80 if title.lower().startswith(needle) else 60 if needle in title.lower() else 30)
                    score += min(10,hay.count(needle))
                    values.append({"database":name,"table":table,"knowledge_id":f"{name}:{table}:{fields.get(cols[0])}","title":title[:240],"detail":detail,"fields":fields,"score":score})
            except Exception:
                continue
            values.sort(key=lambda x:(-int(x["score"]),x["title"]))
            if values: per_db[name]=values
        # Diversity-first merge: no early database can monopolize Top-N.
        out=[];seen=set();positions={name:0 for name in per_db}
        while len(out)<limit:
            progressed=False
            for name in self.DB_NAMES:
                rows=per_db.get(name) or [];pos=positions.get(name,0)
                while pos<len(rows):
                    row=rows[pos];pos+=1;positions[name]=pos
                    key=(row["database"],row["knowledge_id"],row["title"])
                    if key in seen: continue
                    seen.add(key);out.append(row);progressed=True;break
                if len(out)>=limit: break
            if not progressed: break
        return out



def create_backup(data_dir: Path, database_path: Path) -> Path:
    data_dir=Path(data_dir); backups=data_dir/"backups"; backups.mkdir(parents=True,exist_ok=True)
    stamp=utc_now().strftime("%Y%m%d-%H%M%S")
    dest=backups/f"srw-backup-{stamp}.zip"
    # SQLite online backup gives a consistent snapshot even with WAL.
    tmp=Path(tempfile.mkdtemp(prefix="srw-backup-")); snap=tmp/"srw_v1.db"
    src=dst=None
    try:
        src=sqlite3.connect(str(database_path)); dst=sqlite3.connect(str(snap)); src.backup(dst)
        dst.close(); dst=None; src.close(); src=None
        write_backup_archive(dest,snap,data_dir/"blobs")
        return dest
    finally:
        if dst is not None: dst.close()
        if src is not None: src.close()
        shutil.rmtree(tmp,ignore_errors=True)


def diagnostics(session: Session, *, data_dir: Path, knowledge_dir: Path, database_path: Path, version: str, schema_revision: str, frontend_dist: Path | None = None, backup_retention: int = 14) -> dict[str,Any]:
    import importlib
    protocol_models = importlib.import_module("srw.modules.protocol.models")
    candidate_models = importlib.import_module("srw.modules.candidate.models")
    data_dir=Path(data_dir); database_path=Path(database_path)
    quick_check="unavailable"
    try:
        con=sqlite3.connect(str(database_path)); quick_check=str(con.execute("PRAGMA quick_check").fetchone()[0]); con.close()
    except Exception as exc:
        quick_check=f"error:{type(exc).__name__}"
    task_rows=session.execute(select(TaskRecord.status,func.count(TaskRecord.id)).group_by(TaskRecord.status)).all()
    task_counts={str(status):int(count) for status,count in task_rows}
    open_statuses={"queued","running","waiting_provider","failed"}
    blob_root=data_dir/"blobs"; blob_files=0; blob_bytes=0
    if blob_root.exists():
        for path in blob_root.rglob("*"):
            if path.is_file():
                blob_files+=1
                try: blob_bytes+=path.stat().st_size
                except OSError: pass
    blob_hashes=session.scalars(select(candidate_models.Source.blob_hash).where(candidate_models.Source.blob_hash.is_not(None))).all()
    missing=0
    for digest in {str(x) for x in blob_hashes if x}:
        if not (blob_root/digest[:2]/digest).is_file(): missing+=1
    data_bytes=0
    if data_dir.exists():
        for path in data_dir.rglob("*"):
            if path.is_file():
                try: data_bytes+=path.stat().st_size
                except OSError: pass
    backup_root=data_dir/"backups"; backup_root.mkdir(parents=True,exist_ok=True)
    backups=list(backup_root.glob("*.zip"))
    frontend_ok=True
    if frontend_dist is not None:
        fd=Path(frontend_dist); frontend_ok=(fd/"index.html").is_file()
    knowledge_status=KnowledgeService(knowledge_dir).status()
    knowledge_ready=all((Path(knowledge_dir)/name/"knowledge.db").is_file() for name in ("taxonomy","job_info","competency","market_reference","reference"))
    checks=[
      {"name":"database_integrity","status":"ok" if quick_check.lower()=="ok" else "error","detail":quick_check},
      {"name":"data_directory","status":"ok" if data_dir.is_dir() else "error","detail":str(data_dir)},
      {"name":"frontend_assets","status":"ok" if frontend_ok else "error","detail":str(frontend_dist or "not-configured")},
      {"name":"background_tasks","status":"ok" if task_counts.get("failed",0)==0 else "warning","detail":task_counts},
      {"name":"backups","status":"ok","detail":{"count":len(backups),"retention":backup_retention}},
      {"name":"knowledge","status":"ok" if knowledge_ready else "warning","detail":knowledge_status},
    ]
    overall="error" if any(x["status"]=="error" for x in checks) else ("warning" if any(x["status"]=="warning" for x in checks) else "ok")
    return {
      "overall_status":overall,"checks":checks,"local_only":True,"backup_retention":backup_retention,
      "version":version,"schema_revision":schema_revision,
      "counts":{
        "projects":session.scalar(select(func.count(protocol_models.Project.id))) or 0,
        "candidates":session.scalar(select(func.count(candidate_models.Candidate.id))) or 0,
        "sources":session.scalar(select(func.count(candidate_models.Source.id))) or 0,
        "claims":session.scalar(select(func.count(candidate_models.Claim.id))) or 0,
        "tasks":session.scalar(select(func.count(TaskRecord.id))) or 0,
      },
      "database":{"quick_check":quick_check,"size_bytes":database_path.stat().st_size if database_path.is_file() else 0},
      "tasks":{"by_status":task_counts,"open":sum(task_counts.get(x,0) for x in open_statuses),"total":sum(task_counts.values())},
      "storage":{"data_bytes":data_bytes,"blob_files":blob_files,"blob_bytes":blob_bytes,"missing_source_blobs":missing},
      "pending_restore":(data_dir/"pending_restore.json").is_file(),
      "paths":{"data":str(data_dir),"knowledge":str(Path(knowledge_dir))},
      "knowledge":knowledge_status,
    }
