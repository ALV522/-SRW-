"""Candidate intake remains usable before protocol publication, without decisions."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]


class PrepublicationCandidateWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self.data = self.root / "data"
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{(self.root / 'test.db').as_posix()}",
            data_dir=self.data, knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )

    def create_pair(self, client):
        project = client.post("/api/v1/projects", json={
            "title": "未发布标准项目", "role_title": "分析师", "brief_summary": "允许先收件"
        })
        self.assertEqual(project.status_code, 200, project.text)
        pid = project.json()["project_id"]
        draft = project.json()["draft_revision_id"]
        candidate = client.post(f"/api/v1/projects/{pid}/candidates", json={
            "display_name": "模拟候选人"
        })
        self.assertEqual(candidate.status_code, 200, candidate.text)
        return pid, candidate.json()["candidate_id"], draft

    def test_empty_candidate_workspace_is_readable_and_not_decision_ready(self):
        with TestClient(self.app) as client:
            pid, cid, draft = self.create_pair(client)
            response = client.get(f"/api/v1/candidates/{cid}/workspace")
            self.assertEqual(response.status_code, 200, response.text)
            workspace = response.json()
            self.assertEqual(workspace["sources"], [])
            self.assertEqual(workspace["decision_context_hash"], "")
            self.assertFalse(workspace["decision_ready"])
            self.assertEqual(workspace["next_action"]["type"], "WAIT_FOR_INPUT")
            self.assertIn("未正式发布", workspace["readiness_label"])

    def test_material_remains_visible_without_published_protocol(self):
        with TestClient(self.app) as client:
            pid, cid, draft = self.create_pair(client)
            intake = client.post(f"/api/v1/candidates/{cid}/sources/text", json={
                "text_content": "模拟候选人具有结构化产品分析经验",
                "filename": "sample.txt", "source_kind": "resume",
                "publish_material": True,
            })
            self.assertEqual(intake.status_code, 200, intake.text)
            response = client.get(f"/api/v1/candidates/{cid}/workspace")
            self.assertEqual(response.status_code, 200, response.text)
            w = response.json()
            self.assertFalse(w["decision_ready"])
            self.assertEqual(w["decision_context_hash"], "")
            self.assertEqual(len(w["sources"]), 1)
            self.assertTrue(w["sources"][0]["in_current_material"])
            self.assertIn("结构化产品分析经验", w["sources"][0]["text_preview"])

            publish = client.post(f"/api/v1/protocol-revisions/{draft}/publish")
            self.assertEqual(publish.status_code, 200, publish.text)
            updated = client.get(f"/api/v1/candidates/{cid}/workspace")
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(len(updated.json()["decision_context_hash"]), 64)
            self.assertEqual(len(updated.json()["sources"]), 1)

    def test_unknown_candidate_still_returns_not_found(self):
        with TestClient(self.app) as client:
            response = client.get("/api/v1/candidates/does-not-exist/workspace")
            self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
