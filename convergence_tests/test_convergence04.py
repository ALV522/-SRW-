import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, select

from srw.kernel.hashing import content_hash
from srw.modules.ai_runs.models import AiRun
from srw.modules.ai_runs.service import start_ai_run, finish_ai_run, fail_ai_run, list_ai_runs
from srw.modules.candidate.commands import add_claim
from srw.modules.candidate.models import Candidate, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.modules.decision.commands import record_assessment
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.human_decision import make_human_decision
from srw.modules.decision.lineage import get_decision_history, reaffirm_latest_decision
from srw.modules.decision.verification import carry_forward_grounded_judgments
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.db.schema import V1_SCHEMA_REVISION, V1SchemaMeta, create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory
from srw.surfaces.candidate_workspace import get_candidate_workspace


class Convergence04Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.engine = create_v1_engine(f"sqlite+pysqlite:///{self.db}")
        create_v1_schema(self.engine)
        self.factory = create_v1_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _published_project(self, session):
        project = Project(title="Analyst", status="open")
        session.add(project); session.flush()
        repo = ProtocolRepository(session)
        draft = repo.create_draft(project.id, {
            "brief": {"title": "Analyst", "summary": ""},
            "criteria": [
                {"criterion_key": "exp", "name": "Experience", "weight": 1, "decision_critical": True},
            ],
            "assessment_stages": [],
            "decision_policy": {"human_final": True},
        })
        repo.publish(draft.id)
        return project

    def _candidate_with_claim(self, session, project_id):
        candidate = Candidate(project_id=project_id, display_name="Candidate")
        session.add(candidate); session.flush()
        text = "Candidate has three years of recruiting experience."
        source = Source(
            candidate_id=candidate.id,
            source_kind="resume",
            content_hash=content_hash({"text": text}),
            media_type="text/plain",
            text_content=text,
            metadata_json=json.dumps({"filename": "resume.txt"}),
        )
        session.add(source); session.flush()
        MaterialRepository(session).publish_revision(candidate.id, [source.id], {"test": True})
        claim = add_claim(
            session,
            candidate.id,
            source.id,
            "three years recruiting experience",
            locator={"quote": "three years of recruiting experience"},
            authority="human",
        )
        claim.confirmation_state = "confirmed"
        session.flush()
        return candidate, source, claim

    def test_ai_run_ledger_hashes_input_and_never_stores_raw_payload(self):
        secret_input = "张三 13812345678 private resume text"
        with self.factory() as s:
            project = self._published_project(s)
            candidate, source, _ = self._candidate_with_claim(s, project.id)
            run = start_ai_run(
                s,
                task_type="evidence_extract",
                project_id=project.id,
                candidate_id=candidate.id,
                source_id=source.id,
                provider_kind="openai_compatible",
                model_name="test-model",
                input_material=secret_input,
                input_safety_meta={"privacy_projection": True, "redaction_counts": {"phone": 1}},
            )
            run_id = run.id
            s.commit()
        with self.factory() as s:
            finish_ai_run(s, run_id, {"created": 2, "claim_ids": ["a", "b"]}, latency_ms=123)
            s.commit()
            row = s.get(AiRun, run_id)
            self.assertEqual(row.status, "succeeded")
            self.assertEqual(row.latency_ms, 123)
            self.assertEqual(len(row.input_hash), 64)
            self.assertEqual(len(row.output_hash), 64)
            self.assertNotEqual(row.input_hash, secret_input)
            serialized = "|".join(str(getattr(row, col.name) or "") for col in row.__table__.columns)
            self.assertNotIn(secret_input, serialized)
            self.assertNotIn("13812345678", serialized)
            self.assertEqual(len(list_ai_runs(s, candidate_id=row.candidate_id)), 1)

    def test_failed_ai_run_keeps_error_metadata_without_raw_provider_body(self):
        with self.factory() as s:
            run = start_ai_run(s, task_type="evidence_extract", input_material="private material")
            run_id = run.id
            s.commit()
        with self.factory() as s:
            fail_ai_run(s, run_id, RuntimeError("remote failed"), latency_ms=9, error_code="provider_failure")
            s.commit()
            row = s.get(AiRun, run_id)
            self.assertEqual(row.status, "failed")
            self.assertEqual(row.error_class, "RuntimeError")
            self.assertEqual(row.error_code, "provider_failure")
            self.assertFalse(hasattr(row, "raw_input"))
            self.assertFalse(hasattr(row, "raw_output"))

    def test_decision_becomes_stale_then_can_be_explicitly_reaffirmed(self):
        with self.factory() as s:
            project = self._published_project(s)
            candidate, source, claim = self._candidate_with_claim(s, project.id)
            record_assessment(
                s, candidate.id, "exp", status="met", evidence_level="strong",
                reason="resume evidence", gap="", claim_ids=[claim.id], actor="reviewer",
                evaluation_policy_revision="policy.v1",
            )
            old_ctx = get_current_decision_context(s, candidate.id, evaluation_policy_revision="policy.v1")
            old_decision = make_human_decision(
                s, candidate.id, decision="advance", reason="meets current bar",
                actor="reviewer", evaluation_policy_revision="policy.v1",
            )
            # Add new material while retaining the grounded source, then explicitly carry forward grounded judgments.
            extra = Source(
                candidate_id=candidate.id, source_kind="supplement",
                content_hash=content_hash({"text": "portfolio"}), media_type="text/plain",
                text_content="portfolio", metadata_json="{}",
            )
            s.add(extra); s.flush()
            current_ids = get_current_source_ids(s, candidate.id)
            material = MaterialRepository(s).publish_revision(candidate.id, [*current_ids, extra.id], {"test": "new material"})
            new_ctx = get_current_decision_context(s, candidate.id, evaluation_policy_revision="policy.v1")
            self.assertNotEqual(old_ctx.hash, new_ctx.hash)
            carry_forward_grounded_judgments(
                s, candidate.id, old_context_hash=old_ctx.hash, new_context_hash=new_ctx.hash,
                new_material_revision_id=material.id, actor="system",
            )
            workspace = get_candidate_workspace(s, candidate.id, evaluation_policy_revision="policy.v1")
            self.assertEqual(workspace.decision_label, "")
            self.assertTrue(workspace.decision_reaffirmable)
            self.assertEqual(workspace.stale_decision_id, old_decision.id)
            self.assertEqual(workspace.stale_decision_label, "继续推进")
            self.assertTrue(workspace.criteria[0].carried_forward)
            self.assertEqual(workspace.criteria[0].origin, "carried_forward")

            reaffirmed = reaffirm_latest_decision(
                s, candidate.id, actor="reviewer2", reason="new material does not change the conclusion",
                evaluation_policy_revision="policy.v1",
            )
            self.assertEqual(reaffirmed.decision, "advance")
            self.assertEqual(reaffirmed.reaffirmed_from_decision_id, old_decision.id)
            history = get_decision_history(s, candidate.id, evaluation_policy_revision="policy.v1")
            self.assertEqual(history[0].decision_id, reaffirmed.id)
            self.assertTrue(history[0].is_current_context)
            self.assertTrue(history[1].stale)

    def test_reaffirmation_is_blocked_if_current_context_lacks_required_evidence(self):
        with self.factory() as s:
            project = self._published_project(s)
            candidate, source, claim = self._candidate_with_claim(s, project.id)
            record_assessment(
                s, candidate.id, "exp", status="met", evidence_level="strong", reason="ok", gap="",
                claim_ids=[claim.id], actor="reviewer", evaluation_policy_revision="policy.v1",
            )
            make_human_decision(s, candidate.id, decision="advance", reason="old decision", actor="reviewer", evaluation_policy_revision="policy.v1")
            # Replace current material with a different source, so grounded judgment cannot be carried forward.
            replacement = Source(
                candidate_id=candidate.id, source_kind="resume", content_hash=content_hash({"text": "replacement"}),
                media_type="text/plain", text_content="replacement", metadata_json="{}",
            )
            s.add(replacement); s.flush()
            MaterialRepository(s).publish_revision(candidate.id, [replacement.id], {"test": "replacement"})
            with self.assertRaises(Exception):
                reaffirm_latest_decision(
                    s, candidate.id, actor="reviewer2", reason="try", evaluation_policy_revision="policy.v1"
                )

    def test_0011_database_upgrades_to_0012_lineage_and_ai_run(self):
        old = Path(self.tmp.name) / "old0011.db"
        conn = sqlite3.connect(old)
        try:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision VARCHAR(40) PRIMARY KEY NOT NULL, created_at DATETIME NOT NULL)")
            conn.execute("INSERT INTO v1_schema_meta(schema_revision,created_at) VALUES ('v1_0011','2026-10-16 00:00:00')")
            conn.execute("CREATE TABLE criterion_judgment (id VARCHAR(36) PRIMARY KEY NOT NULL, project_id VARCHAR(36) NOT NULL, candidate_id VARCHAR(36) NOT NULL, criterion_key VARCHAR(128) NOT NULL, decision_context_hash VARCHAR(64) NOT NULL, status VARCHAR(20) NOT NULL, evidence_level VARCHAR(20) NOT NULL DEFAULT 'none', reason TEXT NOT NULL DEFAULT '', gap TEXT NOT NULL DEFAULT '', updated_at DATETIME NOT NULL)")
            conn.execute("CREATE TABLE human_decision (id VARCHAR(36) PRIMARY KEY NOT NULL, project_id VARCHAR(36) NOT NULL, candidate_id VARCHAR(36) NOT NULL, decision_context_hash VARCHAR(64) NOT NULL, decision VARCHAR(32) NOT NULL, reason TEXT NOT NULL DEFAULT '', override BOOLEAN NOT NULL DEFAULT 0, actor VARCHAR(120) NOT NULL DEFAULT 'human', created_at DATETIME NOT NULL)")
            conn.commit()
        finally:
            conn.close()
        engine = create_v1_engine(f"sqlite+pysqlite:///{old}")
        try:
            create_v1_schema(engine)
            judgment_cols = {c["name"] for c in inspect(engine).get_columns("criterion_judgment")}
            decision_cols = {c["name"] for c in inspect(engine).get_columns("human_decision")}
            tables = set(inspect(engine).get_table_names())
            self.assertIn("origin", judgment_cols)
            self.assertIn("carried_forward_from_judgment_id", judgment_cols)
            self.assertIn("reaffirmed_from_decision_id", decision_cols)
            self.assertIn("ai_run", tables)
            factory = create_v1_session_factory(engine)
            with factory() as s:
                meta = s.scalar(select(V1SchemaMeta).limit(1))
                self.assertEqual(meta.schema_revision, V1_SCHEMA_REVISION)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
