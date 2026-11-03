"""#198: manual Claim proposal is grounded, auditable and never auto-confirmed.

Real TestClient HTTP + disposable SQLite; no AI Provider, private resumes or
production Knowledge. Windows Native GUI and browser click paths remain NOT RUN.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.candidate.repository import MaterialRepository
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory, v1_session_scope
from srw.runtime.business_session_gateway import CSRF_COOKIE_NAME, PAIRING_PATH

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "Synthetic candidate shipped a payment service for 4 years."


class ManualClaimHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-manual-claim-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.data = root / "data"
        self.data.mkdir()
        self.database = self.data / "manual.db"
        self.database_url = f"sqlite+pysqlite:///{self.database.as_posix()}"
        with patch.dict(os.environ, {"RECRUITMENT_SESSION_ENFORCE": "0", "SRW_BACKGROUND_WORKER": "0"}):
            app = create_v1_app(
                self.database_url, data_dir=self.data,
                knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
                frontend_dist=ROOT / "frontend" / "dist",
            )
        self.client = self.enterContext(TestClient(app))
        project = self.client.post("/api/v1/projects", json={"title": "Manual", "role_title": "Engineer"})
        self.assertEqual(project.status_code, 200, project.text)
        self.pid = project.json()["project_id"]
        candidate = self.client.post(f"/api/v1/projects/{self.pid}/candidates",
                                     json={"display_name": "Synthetic"})
        self.assertEqual(candidate.status_code, 200, candidate.text)
        self.cid = candidate.json()["candidate_id"]
        source = self.client.post(
            f"/api/v1/candidates/{self.cid}/sources/text",
            json={"text_content": SAMPLE, "publish_material": True},
        )
        self.assertEqual(source.status_code, 200, source.text)
        self.sid = source.json()["source_id"]
        self.url = f"/api/v1/candidates/{self.cid}/claims/manual"

    def payload(self, **overrides):
        return {
            "source_id": self.sid, "normalized_text": "Shipped a payment service",
            "locator": {"quote": "shipped a payment service"}, **overrides,
        }

    def post(self, **overrides):
        return self.client.post(self.url, json=self.payload(**overrides))

    def rows(self, table):
        with sqlite3.connect(self.database) as connection:
            return connection.execute(f"SELECT * FROM {table}").fetchall()

    def audit(self):
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                "SELECT actor, payload_json FROM audit_event WHERE event_type='CLAIM_PROPOSED_MANUALLY'"
            ).fetchall()

    def test_grounded_proposal_is_unreviewed_and_review_remains_explicit(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        claim = response.json()
        self.assertEqual(claim["confirmation_state"], "unreviewed")
        self.assertEqual(claim["authority"], "human_proposal")
        self.assertFalse(claim["duplicate"])
        locator = self.client.get(f"/api/v1/claims/{claim['claim_id']}/grounding")
        self.assertEqual(locator.status_code, 200, locator.text)
        self.assertEqual(locator.json()["locator"]["quote"], "shipped a payment service")
        audits = self.audit()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0][0], "human")
        self.assertEqual(json.loads(audits[0][1])["source_id"], self.sid)
        self.assertNotIn("shipped a payment service", audits[0][1])
        reviewed = self.client.post(f"/api/v1/claims/{claim['claim_id']}/review",
                                    json={"accepted": True, "actor": "human"})
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["confirmation_state"], "confirmed")

    def test_duplicate_is_idempotent_and_does_not_duplicate_audit(self):
        first, second = self.post(), self.post()
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(first.json()["claim_id"], second.json()["claim_id"])
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(len(self.audit()), 1)

    def test_bad_inputs_fail_closed_without_claim_or_audit(self):
        cases = [
            ({}, 422), ({"source_id": ""}, 422),
            ({"normalized_text": ""}, 422),
            ({"locator": {"quote": "invented experience"}}, 409),
            ({"locator": {"quote": "shipped a payment service", "char_start": 0}}, 409),
            ({"locator": {"quote": "shipped a payment service", "page": 999}}, 409),
            ({"locator": {"quote": "shipped a payment service", "unsafe": "x"}}, 422),
            ({"actor": "administrator"}, 422),
        ]
        for change, expected in cases:
            with self.subTest(change=change):
                response = self.client.post(self.url, json=self.payload(**change))
                self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(len(self.rows("claim")), 0)
        self.assertEqual(len(self.audit()), 0)

    def test_foreign_source_and_archived_candidate_rejected(self):
        other = self.client.post(f"/api/v1/projects/{self.pid}/candidates",
                                 json={"display_name": "Other"}).json()["candidate_id"]
        foreign = self.client.post(
            f"/api/v1/candidates/{other}/sources/text",
            json={"text_content": SAMPLE, "publish_material": True},
        ).json()["source_id"]
        self.assertEqual(self.post(source_id=foreign).status_code, 409)
        self.assertEqual(self.client.post(f"/api/v1/candidates/{self.cid}/archive").status_code, 200)
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(len(self.rows("claim")), 0)

    def test_old_source_and_missing_current_material_rejected(self):
        later = self.client.post(
            f"/api/v1/candidates/{self.cid}/sources/text",
            json={"text_content": "Synthetic later correction", "publish_material": False},
        )
        self.assertEqual(later.status_code, 200, later.text)
        engine = create_v1_engine(self.database_url)
        try:
            with v1_session_scope(create_v1_session_factory(engine)) as session:
                MaterialRepository(session).publish_revision(
                    self.cid, [later.json()["source_id"]], provenance={"test": "stale"},
                )
        finally:
            engine.dispose()
        self.assertEqual(self.post().status_code, 409)
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE candidate SET current_material_revision_id=NULL WHERE id=?", (self.cid,))
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(len(self.rows("claim")), 0)

    def test_business_session_gate_rejects_anonymous_and_csrf_writes(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-manual-session-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        data = root / "data"
        data.mkdir()
        with patch.dict(os.environ, {"RECRUITMENT_SESSION_ENFORCE": "1", "SRW_BACKGROUND_WORKER": "0"}):
            app = create_v1_app(
                f"sqlite+pysqlite:///{(data / 'session.db').as_posix()}",
                data_dir=data,
                knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
                frontend_dist=ROOT / "frontend" / "dist",
            )
        with TestClient(app) as client:
            denied = client.post(self.url, json=self.payload())
            self.assertEqual(denied.status_code, 401, denied.text)
            code = app.state.business_gateway.issue_pairing_code()
            paired = client.post(PAIRING_PATH, json={"code": code})
            self.assertEqual(paired.status_code, 200, paired.text)
            denied_csrf = client.post(self.url, json=self.payload(), headers={"origin": "http://testserver"})
            self.assertEqual(denied_csrf.status_code, 403, denied_csrf.text)
            self.assertTrue(client.cookies.get(CSRF_COOKIE_NAME))
        with sqlite3.connect(data / "session.db") as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM claim").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
