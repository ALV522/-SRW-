"""Failed candidate intake must never persist unreferenced applicant blobs."""
from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app

ROOT = Path(__file__).resolve().parents[1]


class CandidateFilePrevalidationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="srw-intake-prevalidate-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.data = root / "data"
        self.data.mkdir()
        knowledge = create_minimal_knowledge_tree(root / "knowledge" / "active")
        app = create_v1_app(
            f"sqlite+pysqlite:///{(self.data / 'v1.db').as_posix()}",
            data_dir=self.data, knowledge_dir=knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(app))
        project = self.client.post("/api/v1/projects", json={
            "title": "Synthetic applicant intake", "role_title": "Test role"})
        self.assertEqual(project.status_code, 200, project.text)
        self.pid = project.json()["project_id"]

    def item(self, raw: bytes) -> dict:
        return {"filename": "synthetic-resume.txt", "media_type": "text/plain",
                "base64": base64.b64encode(raw).decode("ascii")}

    def assert_absent(self, raw: bytes) -> None:
        digest = hashlib.sha256(raw).hexdigest()
        self.assertFalse((self.data / "blobs" / digest[:2] / digest).exists(),
                         "An unsuccessful request must not persist private applicant data")

    def test_unknown_candidate_rejects_before_writing_applicant_bytes(self):
        raw = b"SYNTHETIC-CANDIDATE-NOT-FOUND-" + uuid.uuid4().bytes
        response = self.client.post(
            f"/api/v1/candidates/{uuid.uuid4()}/files", json=self.item(raw))
        self.assertEqual(response.status_code, 404, response.text)
        self.assert_absent(raw)

    def test_unknown_batch_project_rejects_before_blob_write(self):
        raw = b"SYNTHETIC-PROJECT-NOT-FOUND-" + uuid.uuid4().bytes
        response = self.client.post(
            f"/api/v1/projects/{uuid.uuid4()}/candidates/batch-intake",
            json={"items": [self.item(raw)]})
        self.assertEqual(response.status_code, 404, response.text)
        self.assert_absent(raw)

    def test_invalid_second_batch_item_does_not_persist_first_item(self):
        raw = b"SYNTHETIC-FIRST-ITEM-" + uuid.uuid4().bytes
        response = self.client.post(
            f"/api/v1/projects/{self.pid}/candidates/batch-intake",
            json={"items": [self.item(raw), {"filename": "bad-second.txt", "base64": "!BAD!"}]})
        self.assertEqual(response.status_code, 409, response.text)
        self.assert_absent(raw)


    def test_valid_batch_still_stores_original_file_and_queues_work(self):
        raw = b"SYNTHETIC-VALID-BATCH-" + uuid.uuid4().bytes
        response = self.client.post(
            f"/api/v1/projects/{self.pid}/candidates/batch-intake",
            json={"items": [self.item(raw)]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["item_count"], 1)
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual((self.data / "blobs" / digest[:2] / digest).read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
