"""Transactional If-Match CAS (ADR-0003 S2): the 412 conflict matrix.

Every covered write refuses a stale precondition inside the transaction, so a
412 leaves state and audit untouched (no false audit). When no If-Match is sent
the behaviour is exactly as before, which keeps every existing client valid
until the frontend ships the header (phase 2 completion).

Covered here: protocol draft update, protocol publish, human decision, and the
verification note. Tokens are the ones the read models already expose:
``draft.token`` (revision identity + content hash) and the candidate
workspace's ``decision_context_hash``.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app


class RevisionCasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
        )
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        self.client = client

    # -- helpers -------------------------------------------------------
    def _create_project(self) -> str:
        response = self.client.post(
            "/api/v1/projects", json={"title": "CAS 合成岗位", "role_title": "高级工程师"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["project_id"]

    def _protocol_workspace(self, project_id: str) -> dict:
        response = self.client.get(f"/api/v1/projects/{project_id}/protocol-workspace")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_candidate(self, project_id: str) -> str:
        response = self.client.post(
            f"/api/v1/projects/{project_id}/candidates", json={"display_name": "CAS 合成人"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["candidate_id"]

    def _publish_protocol(self, project_id: str) -> None:
        draft = self._protocol_workspace(project_id)["draft"]
        patched = self.client.patch(
            f"/api/v1/protocol-revisions/{draft['revision_id']}",
            json={
                "payload": {
                    "brief": {"title": "CAS 合成岗位"},
                    "criteria": [],
                    "assessment_stages": [],
                },
                "provenance": {},
            },
            headers={"If-Match": draft["token"]},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        moved = self._protocol_workspace(project_id)["draft"]["token"]
        published = self.client.post(
            f"/api/v1/protocol-revisions/{draft['revision_id']}/publish",
            headers={"If-Match": moved},
        )
        self.assertEqual(published.status_code, 200, published.text)

    def _audit_count(self, project_id: str) -> int:
        response = self.client.get(f"/api/v1/projects/{project_id}/audit")
        self.assertEqual(response.status_code, 200, response.text)
        return len(response.json().get("events") or response.json().get("items") or [])

    # -- protocol draft update -----------------------------------------
    def test_protocol_update_if_match_lifecycle(self):
        pid = self._create_project()
        workspace = self._protocol_workspace(pid)
        draft_id = workspace["draft"]["revision_id"]
        token = workspace["draft"]["token"]
        self.assertIn(":", token)

        payload = {
            "brief": {"title": "CAS 合成岗位"},
            "criteria": [{"criterion_key": "c1", "name": "第一条", "definition": "定义一"}],
            "assessment_stages": ["screening"],
            "decision_policy": {},
            "recruitment_context": {},
        }

        fresh = self.client.patch(
            f"/api/v1/protocol-revisions/{draft_id}",
            json={"payload": payload, "provenance": {"origin": "cas-test"}},
            headers={"If-Match": token},
        )
        self.assertEqual(fresh.status_code, 200, fresh.text)
        after = self._protocol_workspace(pid)["draft"]
        self.assertNotEqual(after["token"], token, "a successful edit must move the token")

        stale = self.client.patch(
            f"/api/v1/protocol-revisions/{draft_id}",
            json={"payload": {**payload, "criteria": []}, "provenance": {}},
            headers={"If-Match": token},
        )
        self.assertEqual(stale.status_code, 412, stale.text)
        self.assertEqual(stale.json()["error"]["code"], "revision_conflict")
        # Nothing was written: the criteria from the successful edit survive.
        self.assertEqual(len(self._protocol_workspace(pid)["draft"]["criteria"]), 1)

        garbage = self.client.patch(
            f"/api/v1/protocol-revisions/{draft_id}",
            json={"payload": payload, "provenance": {}},
            headers={"If-Match": '"not-a-real-token"'},
        )
        self.assertEqual(garbage.status_code, 412, garbage.text)

        # No precondition at all keeps today's behaviour.
        unguarded = self.client.patch(
            f"/api/v1/protocol-revisions/{draft_id}",
            json={"payload": {**payload, "criteria": []}, "provenance": {}},
        )
        self.assertEqual(unguarded.status_code, 200, unguarded.text)
        self.assertEqual(self._protocol_workspace(pid)["draft"]["criteria"], [])

    def test_protocol_update_conflict_produces_no_audit(self):
        pid = self._create_project()
        draft = self._protocol_workspace(pid)["draft"]
        payload = {"brief": {"title": "CAS 合成岗位"}, "criteria": [], "assessment_stages": []}
        self.client.patch(
            f"/api/v1/protocol-revisions/{draft['revision_id']}",
            json={"payload": payload, "provenance": {}},
            headers={"If-Match": draft["token"]},
        )
        moved = self._protocol_workspace(pid)["draft"]["token"]
        before = self._audit_count(pid)
        conflict = self.client.patch(
            f"/api/v1/protocol-revisions/{draft['revision_id']}",
            json={"payload": payload, "provenance": {}},
            headers={"If-Match": moved},
        )
        # The token above is the CURRENT one; use a deliberately stale variant:
        # re-read is unnecessary - simulate a stale client by replaying the old token.
        stale = self.client.patch(
            f"/api/v1/protocol-revisions/{draft['revision_id']}",
            json={"payload": payload, "provenance": {}},
            headers={"If-Match": draft["token"]},
        )
        self.assertEqual(stale.status_code, 412, stale.text)
        self.assertEqual(self._audit_count(pid), before, "a 412 must not write audit events")
        self.assertEqual(conflict.status_code, 200, conflict.text)

    def test_protocol_publish_if_match(self):
        pid = self._create_project()
        draft = self._protocol_workspace(pid)["draft"]
        payload = {"brief": {"title": "CAS 合成岗位"}, "criteria": [], "assessment_stages": []}
        self.client.patch(
            f"/api/v1/protocol-revisions/{draft['revision_id']}",
            json={"payload": payload, "provenance": {}},
            headers={"If-Match": draft["token"]},
        )
        stale = self._protocol_workspace(pid)["draft"]["token"]

        refused = self.client.post(
            f"/api/v1/protocol-revisions/{draft['revision_id']}/publish",
            headers={"If-Match": draft["token"]},
        )
        self.assertEqual(refused.status_code, 412, refused.text)

        published = self.client.post(
            f"/api/v1/protocol-revisions/{draft['revision_id']}/publish",
            headers={"If-Match": stale},
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["state"], "published")

    # -- human decision -------------------------------------------------
    def test_decision_if_match_tracks_the_decision_context(self):
        pid = self._create_project()
        self._publish_protocol(pid)
        cid = self._create_candidate(pid)
        # A decision context only exists once a material revision is published.
        seeded = self.client.post(
            f"/api/v1/candidates/{cid}/sources/text",
            json={
                "text_content": "CAS 合成材料：结构化调研经历。",
                "filename": "cas-seed.txt",
                "publish_material": True,
            },
        )
        self.assertEqual(seeded.status_code, 200, seeded.text)
        workspace = self.client.get(f"/api/v1/candidates/{cid}/workspace").json()
        context = workspace["decision_context_hash"]
        self.assertTrue(context)

        first = self.client.post(
            f"/api/v1/candidates/{cid}/decision",
            json={"decision": "hold", "reason": "等待更多证据", "actor": "human"},
            headers={"If-Match": context},
        )
        self.assertEqual(first.status_code, 200, first.text)

        # A new PUBLISHED material revision moves the decision context; the old token is stale.
        source = self.client.post(
            f"/api/v1/candidates/{cid}/sources/text",
            json={
                "text_content": "CAS 合成材料（第二版）：补充访谈细节。",
                "filename": "cas-2.txt",
                "publish_material": True,
            },
        )
        self.assertEqual(source.status_code, 200, source.text)

        stale = self.client.post(
            f"/api/v1/candidates/{cid}/decision",
            json={"decision": "hold", "reason": "陈旧上下文", "actor": "human"},
            headers={"If-Match": context},
        )
        self.assertEqual(stale.status_code, 412, stale.text)
        self.assertEqual(stale.json()["error"]["code"], "revision_conflict")

        moved = self.client.get(f"/api/v1/candidates/{cid}/workspace").json()["decision_context_hash"]
        self.assertNotEqual(moved, context)
        fresh = self.client.post(
            f"/api/v1/candidates/{cid}/decision",
            json={"decision": "hold", "reason": "新上下文下继续等待", "actor": "human"},
            headers={"If-Match": moved},
        )
        self.assertEqual(fresh.status_code, 200, fresh.text)

    def test_verification_note_if_match(self):
        pid = self._create_project()
        self._publish_protocol(pid)
        cid = self._create_candidate(pid)
        seeded = self.client.post(
            f"/api/v1/candidates/{cid}/sources/text",
            json={
                "text_content": "CAS 合成材料：结构化调研经历。",
                "filename": "cas-seed.txt",
                "publish_material": True,
            },
        )
        self.assertEqual(seeded.status_code, 200, seeded.text)
        context = self.client.get(f"/api/v1/candidates/{cid}/workspace").json()["decision_context_hash"]
        self.assertTrue(context)

        accepted = self.client.post(
            f"/api/v1/candidates/{cid}/verifications",
            json={
                "criterion_key": "c1",
                "note": "CAS 合成核实记录",
                "status": "met",
                "evidence_level": "documented",
                "reason": "有材料支撑",
                "actor": "human",
            },
            headers={"If-Match": context},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)

        stale = self.client.post(
            f"/api/v1/candidates/{cid}/verifications",
            json={
                "criterion_key": "c1",
                "note": "陈旧上下文写入",
                "status": "met",
                "evidence_level": "documented",
                "reason": "有材料支撑",
                "actor": "human",
            },
            headers={"If-Match": "deadbeef"},
        )
        self.assertEqual(stale.status_code, 412, stale.text)


if __name__ == "__main__":
    unittest.main()
