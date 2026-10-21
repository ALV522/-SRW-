"""Candidate comparison and CSV export read models (ADR-0002 slice 4).

Covers the extracted compare_candidates / candidates_csv_text / contact_list_csv_text
surfaces and their thin HTTP adapters. Synthetic SQLite workspaces only.
"""
from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash
from srw.modules.candidate.commands import add_source, create_candidate
from srw.modules.candidate.repository import MaterialRepository
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory
from srw.surfaces.candidate_exports import (
    candidates_csv_text,
    compare_candidates,
    contact_list_csv_text,
    csv_safe_cell,
)

_DRAFT_PAYLOAD = {
    "brief": {"title": "Synthetic role", "summary": ""},
    "recruitment_context": {"role_title": "Synthetic role", "location": "北京"},
    "criteria": [
        {
            "criterion_key": "comm",
            "name": "沟通能力",
            "definition": "清晰表达",
            "decision_critical": True,
            "verification_required": True,
            "verification_probes": [],
        }
    ],
    "assessment_stages": [],
    "decision_policy": {"human_final": True},
}

_POLICY = "policy.v1"


def _parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


class CandidateExportsDomainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        engine = create_v1_engine(f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}")
        self.addCleanup(engine.dispose)
        create_v1_schema(engine)
        self.factory = create_v1_session_factory(engine)
        with self.factory.begin() as session:
            project = Project(title="Synthetic role")
            session.add(project)
            session.flush()
            repo = ProtocolRepository(session)
            draft = repo.create_draft(project.id, dict(_DRAFT_PAYLOAD))
            repo.publish(draft.id)
            self.pid = project.id
            self.cid_a = create_candidate(session, self.pid, "=Candidate(A)").id
            self.cid_b = create_candidate(session, self.pid, "Candidate(B)").id
            for cid in (self.cid_a, self.cid_b):
                source = add_source(
                    session, cid, source_kind="resume",
                    content_hash=content_hash({"synthetic": cid}), text_content="Synthetic resume text",
                )
                MaterialRepository(session).publish_revision(cid, [source.id], {"origin": "synthetic-test"})

    def test_compare_returns_rows_with_criteria_and_note(self):
        with self.factory() as session:
            payload = compare_candidates(session, [self.cid_a, self.cid_b], evaluation_policy_revision=_POLICY)
        self.assertEqual(payload["project_id"], self.pid)
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertEqual(len(payload["criteria"]), 1)
        self.assertEqual(payload["criteria"][0]["criterion_key"], "comm")
        for row in payload["candidates"]:
            self.assertTrue(row["has_material"])
            self.assertEqual(len(row["criteria"]), 1)
            self.assertEqual(row["criteria"][0]["status"], "missing")
            self.assertEqual(row["criteria"][0]["evidence_level"], "none")
        self.assertIn("no automatic hiring decision", payload["note"])

    def test_compare_rejects_cross_project_ids(self):
        with self.factory.begin() as session:
            other = Project(title="Other project")
            session.add(other)
            session.flush()
            stranger = create_candidate(session, other.id, "Stranger").id
        with self.factory() as session:
            with self.assertRaises(V1InvariantError):
                compare_candidates(session, [self.cid_a, stranger], evaluation_policy_revision=_POLICY)

    def test_compare_rejects_unknown_candidate(self):
        with self.factory() as session:
            with self.assertRaises(V1NotFoundError):
                compare_candidates(session, [self.cid_a, "ghost"], evaluation_policy_revision=_POLICY)

    def test_compare_rejects_project_without_published_protocol(self):
        with self.factory.begin() as session:
            bare = Project(title="Bare project")
            session.add(bare)
            session.flush()
            bare_cid = create_candidate(session, bare.id, "Bare").id
            second = create_candidate(session, bare.id, "Bare2").id
        with self.factory() as session:
            with self.assertRaises(V1InvariantError):
                compare_candidates(session, [bare_cid, second], evaluation_policy_revision=_POLICY)

    def test_csv_safe_cell_neutralizes_formula_prefixes(self):
        self.assertEqual(csv_safe_cell("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(csv_safe_cell("+1"), "'+1")
        self.assertEqual(csv_safe_cell("-1"), "'-1")
        self.assertEqual(csv_safe_cell("@x"), "'@x")
        self.assertEqual(csv_safe_cell("plain"), "plain")
        self.assertEqual(csv_safe_cell(None), "")

    def test_candidates_csv_header_and_formula_guard(self):
        with self.factory() as session:
            text = candidates_csv_text(session, project_id=self.pid, evaluation_policy_revision=_POLICY)
        rows = _parse_csv(text)
        self.assertEqual(len(rows), 2)
        self.assertIn("candidate_id", rows[0])
        self.assertIn("criteria_summary", rows[0])
        names = {r["display_name"] for r in rows}
        self.assertIn("'=Candidate(A)", names)
        self.assertIn("Candidate(B)", names)
        self.assertTrue(all(r["has_material"] == "1" for r in rows))
        self.assertTrue(all(r["protocol_revision_id"] for r in rows))

    def test_candidates_csv_unknown_project_is_not_found(self):
        with self.factory() as session:
            with self.assertRaises(V1NotFoundError):
                candidates_csv_text(session, project_id="ghost", evaluation_policy_revision=_POLICY)

    def test_contact_list_csv_renders_queue(self):
        with self.factory() as session:
            text = contact_list_csv_text(session, project_id=self.pid)
        rows = _parse_csv(text)
        self.assertEqual(len(rows), 2)
        self.assertIn("next_action", rows[0])


class CandidateExportsHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        url = f"sqlite+pysqlite:///{(self.root / 'synthetic.db').as_posix()}"
        engine = create_v1_engine(url)
        self.addCleanup(engine.dispose)
        create_v1_schema(engine)
        factory = create_v1_session_factory(engine)
        with factory.begin() as session:
            project = Project(title="Synthetic role")
            session.add(project)
            session.flush()
            repo = ProtocolRepository(session)
            draft = repo.create_draft(project.id, dict(_DRAFT_PAYLOAD))
            repo.publish(draft.id)
            self.pid = project.id
            self.cid_a = create_candidate(session, self.pid, "Alpha").id
            self.cid_b = create_candidate(session, self.pid, "Beta").id
        app = create_v1_app(
            url,
            data_dir=self.root / "data",
            knowledge_dir=create_minimal_knowledge_tree(self.root / "knowledge" / "active"),
        )
        self.client = self.enterContext(TestClient(app))

    def test_compare_route(self):
        response = self.client.get(f"/api/v1/candidates/compare?ids={self.cid_a},{self.cid_b}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["candidates"]), 2)

    def test_compare_route_rejects_single_id(self):
        response = self.client.get(f"/api/v1/candidates/compare?ids={self.cid_a}")
        self.assertEqual(response.status_code, 409, response.text)

    def test_candidates_csv_route(self):
        response = self.client.get(f"/api/v1/projects/{self.pid}/candidates.csv")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn(f"candidates-{self.pid}.csv", response.headers["content-disposition"])
        self.assertEqual(len(_parse_csv(response.text)), 2)

    def test_candidates_csv_route_unknown_project_is_404(self):
        response = self.client.get("/api/v1/projects/ghost/candidates.csv")
        self.assertEqual(response.status_code, 404, response.text)

    def test_contact_list_csv_route(self):
        response = self.client.get(f"/api/v1/projects/{self.pid}/contact-list.csv")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(f"contact-list-{self.pid}.csv", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
