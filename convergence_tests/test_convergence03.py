import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, select

from srw.modules.candidate.models import Candidate, CandidateContact, Source
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.modules.decision.commands import record_assessment
from srw.modules.decision.shortlist import build_ranked_shortlist, publish_ranked_shortlist, list_shortlist_publications
from srw.modules.identity.service import (
    scan_project_identity, list_identity_reviews, resolve_identity_review,
    identity_merge_preview, commit_identity_merge, merged_identity_history,
)
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.recruiting.models import OfferRecord
from srw.runtime.db.schema import V1_SCHEMA_REVISION, V1SchemaMeta, create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory


class Convergence03Test(unittest.TestCase):
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
        project = Project(title="Engineer", status="draft")
        session.add(project); session.flush()
        repo = ProtocolRepository(session)
        draft = repo.create_draft(project.id, {
            "brief": {"title": "Engineer", "summary": ""},
            "criteria": [
                {"criterion_key": "exp", "name": "Experience", "weight": 3, "decision_critical": True},
                {"criterion_key": "comm", "name": "Communication", "weight": 1},
            ],
            "assessment_stages": [],
            "decision_policy": {"human_final": True},
        })
        repo.publish(draft.id)
        return project

    def _candidate_with_material(self, session, project_id, name, text):
        candidate = Candidate(project_id=project_id, display_name=name)
        session.add(candidate); session.flush()
        source = Source(
            candidate_id=candidate.id,
            source_kind="resume",
            content_hash=(name.encode("utf-8").hex() + "0" * 64)[:64],
            media_type="text/plain",
            text_content=text,
            metadata_json=json.dumps({"filename": f"{name}.txt"}, ensure_ascii=False),
        )
        session.add(source); session.flush()
        MaterialRepository(session).publish_revision(candidate.id, [source.id], {"test": True})
        return candidate, source

    def test_identity_merge_preview_and_commit_preserve_history(self):
        with self.factory() as s:
            project = self._published_project(s)
            target, target_source = self._candidate_with_material(s, project.id, "Canonical", "Target resume")
            source, source_source = self._candidate_with_material(s, project.id, "Duplicate", "Source resume")
            s.add_all([
                CandidateContact(candidate_id=target.id, display_name="Canonical", phone="13812345678", email="same@example.com", user_confirmed=True),
                CandidateContact(candidate_id=source.id, display_name="Duplicate", phone="+86 13812345678", email="same@example.com", user_confirmed=True),
                OfferRecord(project_id=project.id, candidate_id=source.id, status="draft", title="Historical Offer", created_by="human"),
            ]); s.flush()

            scan_project_identity(s, project.id, actor="test")
            review = list_identity_reviews(s, project.id, status="pending")[0]
            resolve_identity_review(s, review["review_id"], status="confirmed_same", actor="reviewer", note="checked")
            preview = identity_merge_preview(s, review["review_id"], target_candidate_id=target.id)
            self.assertTrue(preview["can_merge"])
            self.assertEqual(preview["source_current_source_count"], 1)
            self.assertEqual(preview["source_business_history_counts"]["offers"], 1)
            self.assertFalse(preview["effects"]["rewrite_historical_business_records"])

            result = commit_identity_merge(s, review["review_id"], target_candidate_id=target.id, actor="reviewer", note="commit")
            self.assertTrue(result["merged"])
            self.assertFalse(result["history_rewritten"])
            self.assertEqual(len(result["cloned_source_ids"]), 1)
            s.flush()

            source_row = s.get(Candidate, source.id)
            target_row = s.get(Candidate, target.id)
            self.assertTrue(source_row.archived)
            self.assertEqual(source_row.merged_into_candidate_id, target.id)
            self.assertNotEqual(target_row.current_material_revision_id, target.id)
            target_sources = get_current_source_ids(s, target.id)
            self.assertGreaterEqual(len(target_sources), 2)
            historical_offer = s.scalar(select(OfferRecord).where(OfferRecord.title == "Historical Offer"))
            self.assertEqual(historical_offer.candidate_id, source.id)
            history = merged_identity_history(s, target.id)
            self.assertEqual(history[0]["candidate_id"], source.id)
            self.assertEqual(history[0]["business_history_counts"]["offers"], 1)
            resolved = list_identity_reviews(s, project.id)[0]
            self.assertTrue(resolved["merge_performed"])
            self.assertEqual(resolved["canonical_candidate_id"], target.id)

    def test_ranked_shortlist_only_ranks_closed_evidence(self):
        with self.factory() as s:
            project = self._published_project(s)
            a, _ = self._candidate_with_material(s, project.id, "Alpha", "A")
            b, _ = self._candidate_with_material(s, project.id, "Beta", "B")
            c, _ = self._candidate_with_material(s, project.id, "Gamma", "C")
            for key, status, level in [("exp", "met", "strong"), ("comm", "met", "strong")]:
                record_assessment(s, a.id, key, status=status, evidence_level=level, reason="test", gap="", claim_ids=[], actor="human", evaluation_policy_revision="policy.v1")
            for key, status, level in [("exp", "partial", "strong"), ("comm", "met", "strong")]:
                record_assessment(s, b.id, key, status=status, evidence_level=level, reason="test", gap="", claim_ids=[], actor="human", evaluation_policy_revision="policy.v1")
            record_assessment(s, c.id, "exp", status="met", evidence_level="strong", reason="test", gap="", claim_ids=[], actor="human", evaluation_policy_revision="policy.v1")

            preview = build_ranked_shortlist(s, project.id, evaluation_policy_revision="policy.v1")
            self.assertEqual([x["display_name"] for x in preview["ranked"]], ["Alpha", "Beta"])
            self.assertEqual(preview["ranked"][0]["rank"], 1)
            self.assertEqual(preview["ranked"][1]["rank"], 2)
            self.assertEqual([x["display_name"] for x in preview["unranked"]], ["Gamma"])
            self.assertEqual(preview["unranked"][0]["reason"], "evidence_not_closed")
            self.assertFalse(preview["semantics"]["final_decision"])

            publication = publish_ranked_shortlist(s, project.id, evaluation_policy_revision="policy.v1", actor="TA")
            self.assertEqual(publication["ranked_count"], 2)
            self.assertEqual(publication["unranked_count"], 1)
            self.assertEqual(len(list_shortlist_publications(s, project.id)), 1)

    def test_0010_database_upgrades_with_canonical_identity_column(self):
        old = Path(self.tmp.name) / "old0010.db"
        conn = sqlite3.connect(old)
        try:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision VARCHAR(40) PRIMARY KEY NOT NULL, created_at DATETIME NOT NULL)")
            conn.execute("INSERT INTO v1_schema_meta(schema_revision,created_at) VALUES ('v1_0010','2026-10-16 00:00:00')")
            conn.execute("CREATE TABLE project (id VARCHAR(36) PRIMARY KEY NOT NULL, title VARCHAR(200) NOT NULL, status VARCHAR(32) NOT NULL, current_protocol_revision_id VARCHAR(36), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)")
            conn.execute("CREATE TABLE candidate (id VARCHAR(36) PRIMARY KEY NOT NULL, project_id VARCHAR(36) NOT NULL, display_name VARCHAR(200) NOT NULL, archived BOOLEAN NOT NULL, pipeline_stage VARCHAR(32) NOT NULL, current_material_revision_id VARCHAR(36), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)")
            conn.commit()
        finally:
            conn.close()
        engine = create_v1_engine(f"sqlite+pysqlite:///{old}")
        try:
            create_v1_schema(engine)
            columns = {c["name"] for c in inspect(engine).get_columns("candidate")}
            self.assertIn("merged_into_candidate_id", columns)
            factory = create_v1_session_factory(engine)
            with factory() as s:
                meta = s.scalar(select(V1SchemaMeta).limit(1))
                self.assertEqual(meta.schema_revision, V1_SCHEMA_REVISION)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
