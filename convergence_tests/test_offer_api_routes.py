from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.audit.models import AuditEvent
from srw.modules.candidate.models import Candidate
from srw.modules.protocol.models import Project
from srw.modules.recruiting.models import OfferRecord
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]


class OfferApiRouteExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-offer-route-")
        self.root = Path(self.tmp.name)
        self.db = self.root / "offers.db"
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{self.db.as_posix()}",
            data_dir=self.root / "data",
            knowledge_dir=create_minimal_knowledge_tree(self.root / "knowledge" / "active"),
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
        self.factory = create_v1_session_factory(self.engine)
        with self.factory.begin() as session:
            project = Project(title="Offer 路由拆分验收", status="open")
            session.add(project)
            session.flush()
            candidate = Candidate(
                project_id=project.id,
                display_name="合成候选人",
                pipeline_stage="new",
            )
            session.add(candidate)
            session.flush()
            self.candidate_id = candidate.id

    def tearDown(self):
        self.engine.dispose()
        self.app = None
        self.tmp.cleanup()

    def _set_stage(self, stage: str) -> None:
        with self.factory.begin() as session:
            candidate = session.get(Candidate, self.candidate_id)
            candidate.pipeline_stage = stage

    def test_offer_http_adapter_preserves_guards_transitions_audit_and_no_auto_hire(self):
        actor = "synthetic-recruiter"
        with TestClient(self.app) as client:
            missing = client.get("/api/v1/candidates/does-not-exist/offers")
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["error"]["code"], "not_found")

            blocked = client.post(
                f"/api/v1/candidates/{self.candidate_id}/offers",
                json={"title": "合成 Offer", "actor": actor},
            )
            self.assertEqual(blocked.status_code, 409, blocked.text)
            self.assertEqual(blocked.json()["error"]["code"], "invariant_conflict")

            self._set_stage("interview")
            created = client.post(
                f"/api/v1/candidates/{self.candidate_id}/offers",
                json={
                    "title": "合成 Offer",
                    "compensation_note": "仅合成测试",
                    "target_start_date": "2026-12-01",
                    "terms": "人工确认条款",
                    "actor": actor,
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            offer = created.json()
            offer_id = offer["offer_id"]
            self.assertEqual(offer["status"], "draft")
            self.assertEqual(offer["created_by"], actor)

            listed = client.get(f"/api/v1/candidates/{self.candidate_id}/offers")
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual([row["offer_id"] for row in listed.json()["offers"]], [offer_id])

            skipped = client.post(
                f"/api/v1/offers/{offer_id}/status",
                json={"status": "accepted", "actor": actor, "reason": "非法跳级"},
            )
            self.assertEqual(skipped.status_code, 409, skipped.text)
            self.assertEqual(skipped.json()["error"]["code"], "invariant_conflict")

            for status in ("approved", "sent", "accepted"):
                changed = client.post(
                    f"/api/v1/offers/{offer_id}/status",
                    json={"status": status, "actor": actor, "reason": f"人工推进到 {status}"},
                )
                self.assertEqual(changed.status_code, 200, changed.text)
                self.assertEqual(changed.json()["status"], status)

        with self.factory() as session:
            candidate = session.get(Candidate, self.candidate_id)
            self.assertEqual(candidate.pipeline_stage, "interview", "accepted Offer must not auto-hire")
            stored = session.get(OfferRecord, offer_id)
            self.assertEqual(stored.status, "accepted")
            events = list(session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "offer", AuditEvent.entity_id == offer_id)
                .order_by(AuditEvent.created_at)
            ).all())
            self.assertEqual(
                [event.event_type for event in events],
                ["OFFER_CREATED", "OFFER_STATUS_CHANGED", "OFFER_STATUS_CHANGED", "OFFER_STATUS_CHANGED"],
            )
            self.assertTrue(all(event.actor == actor for event in events))


if __name__ == "__main__":
    unittest.main()
