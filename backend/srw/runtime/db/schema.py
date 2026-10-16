from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Engine, String, inspect, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from srw.kernel.clock import utc_now
from srw.runtime.db.base import V1Base
from srw.runtime.db.models_registry import import_v1_models

V1_SCHEMA_REVISION = "v1_0014"


class V1SchemaMeta(V1Base):
    __tablename__ = "v1_schema_meta"

    schema_revision: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


def _ensure_v1_0003_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "job" not in inspector.get_table_names():
        return
    job_columns = {column["name"] for column in inspector.get_columns("job")}
    if "lease_token" not in job_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE job ADD COLUMN lease_token VARCHAR(36)"))




def _ensure_v1_0004_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "claim" not in inspector.get_table_names():
        return
    claim_columns = {column["name"] for column in inspector.get_columns("claim")}
    if "proposal_metadata_json" not in claim_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE claim ADD COLUMN proposal_metadata_json TEXT NOT NULL DEFAULT '{}'"))


def _ensure_v1_0006_task_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "task_record" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("task_record")}
    statements = []
    if "attempt_count" not in columns:
        statements.append("ALTER TABLE task_record ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
    if "started_at" not in columns:
        statements.append("ALTER TABLE task_record ADD COLUMN started_at DATETIME")
    if "finished_at" not in columns:
        statements.append("ALTER TABLE task_record ADD COLUMN finished_at DATETIME")
    if "duration_ms" not in columns:
        statements.append("ALTER TABLE task_record ADD COLUMN duration_ms INTEGER NOT NULL DEFAULT 0")
    if "result_json" not in columns:
        statements.append("ALTER TABLE task_record ADD COLUMN result_json TEXT NOT NULL DEFAULT '{}'")
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))



def _ensure_v1_0007_business_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []
    if "candidate" in tables:
        columns = {column["name"] for column in inspector.get_columns("candidate")}
        if "pipeline_stage" not in columns:
            statements.append("ALTER TABLE candidate ADD COLUMN pipeline_stage VARCHAR(32) NOT NULL DEFAULT 'new'")
    if "recruitment_event" in tables:
        columns = {column["name"] for column in inspector.get_columns("recruitment_event")}
        if "scheduled_at" not in columns:
            statements.append("ALTER TABLE recruitment_event ADD COLUMN scheduled_at DATETIME")
        if "duration_minutes" not in columns:
            statements.append("ALTER TABLE recruitment_event ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 0")
        if "interviewer" not in columns:
            statements.append("ALTER TABLE recruitment_event ADD COLUMN interviewer VARCHAR(200) NOT NULL DEFAULT ''")
        if "location" not in columns:
            statements.append("ALTER TABLE recruitment_event ADD COLUMN location VARCHAR(500) NOT NULL DEFAULT ''")
        if "event_state" not in columns:
            statements.append("ALTER TABLE recruitment_event ADD COLUMN event_state VARCHAR(24) NOT NULL DEFAULT 'completed'")
        if "outcome" not in columns:
            statements.append("ALTER TABLE recruitment_event ADD COLUMN outcome VARCHAR(40) NOT NULL DEFAULT ''")
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
    if "project" in tables:
        with engine.begin() as connection:
            connection.execute(text("UPDATE project SET status='open' WHERE status='active'"))


def _ensure_v1_0008_audit_task_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []
    if "task_record" in tables:
        columns = {column["name"] for column in inspector.get_columns("task_record")}
        if "job_id" not in columns:
            statements.append("ALTER TABLE task_record ADD COLUMN job_id VARCHAR(36)")
        if "cancel_requested" not in columns:
            statements.append("ALTER TABLE task_record ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT 0")
    if "audit_event" in tables:
        columns = {column["name"] for column in inspector.get_columns("audit_event")}
        if "project_id" not in columns:
            statements.append("ALTER TABLE audit_event ADD COLUMN project_id VARCHAR(36)")
        if "candidate_id" not in columns:
            statements.append("ALTER TABLE audit_event ADD COLUMN candidate_id VARCHAR(36)")
    if "reevaluation_draft" in tables:
        columns = {column["name"] for column in inspector.get_columns("reevaluation_draft")}
        if "protocol_revision_id" not in columns:
            statements.append("ALTER TABLE reevaluation_draft ADD COLUMN protocol_revision_id VARCHAR(36) NOT NULL DEFAULT ''")
        if "material_revision_id" not in columns:
            statements.append("ALTER TABLE reevaluation_draft ADD COLUMN material_revision_id VARCHAR(36) NOT NULL DEFAULT ''")
        if "decision_context_hash" not in columns:
            statements.append("ALTER TABLE reevaluation_draft ADD COLUMN decision_context_hash VARCHAR(64) NOT NULL DEFAULT ''")
        if "diff_json" not in columns:
            statements.append("ALTER TABLE reevaluation_draft ADD COLUMN diff_json TEXT NOT NULL DEFAULT '[]'")
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

def _ensure_v1_0011_identity_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "candidate" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("candidate")}
    if "merged_into_candidate_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE candidate ADD COLUMN merged_into_candidate_id VARCHAR(36)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_candidate_merged_into_candidate_id ON candidate (merged_into_candidate_id)"))



def _ensure_v1_0012_lineage_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []
    if "criterion_judgment" in tables:
        columns = {column["name"] for column in inspector.get_columns("criterion_judgment")}
        if "origin" not in columns:
            statements.append("ALTER TABLE criterion_judgment ADD COLUMN origin VARCHAR(32) NOT NULL DEFAULT 'assessment'")
        if "carried_forward_from_judgment_id" not in columns:
            statements.append("ALTER TABLE criterion_judgment ADD COLUMN carried_forward_from_judgment_id VARCHAR(36)")
    if "human_decision" in tables:
        columns = {column["name"] for column in inspector.get_columns("human_decision")}
        if "reaffirmed_from_decision_id" not in columns:
            statements.append("ALTER TABLE human_decision ADD COLUMN reaffirmed_from_decision_id VARCHAR(36)")
    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_criterion_judgment_carried_forward_from_judgment_id ON criterion_judgment (carried_forward_from_judgment_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_human_decision_reaffirmed_from_decision_id ON human_decision (reaffirmed_from_decision_id)"))

def create_v1_schema(engine: Engine) -> None:
    import_v1_models()
    V1Base.metadata.create_all(engine)
    with Session(engine) as session:
        existing = session.scalar(select(V1SchemaMeta).limit(1))
        if existing is None:
            session.add(V1SchemaMeta(schema_revision=V1_SCHEMA_REVISION))
            session.commit()
            return
        if existing.schema_revision in {"v1_0001", "v1_0002", "v1_0003", "v1_0004", "v1_0005", "v1_0006", "v1_0007", "v1_0008", "v1_0009", "v1_0010", "v1_0011", "v1_0012", "v1_0013"}:
            _ensure_v1_0003_columns(engine)
            _ensure_v1_0004_columns(engine)
            _ensure_v1_0006_task_columns(engine)
            _ensure_v1_0007_business_columns(engine)
            _ensure_v1_0008_audit_task_columns(engine)
            _ensure_v1_0011_identity_columns(engine)
            _ensure_v1_0012_lineage_columns(engine)
            V1Base.metadata.create_all(engine)
            existing.schema_revision = V1_SCHEMA_REVISION
            session.commit()
            return
        if existing.schema_revision != V1_SCHEMA_REVISION:
            raise RuntimeError(
                f"v1 schema revision mismatch: {existing.schema_revision} != {V1_SCHEMA_REVISION}"
            )
