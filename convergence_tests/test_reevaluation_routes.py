"""Reevaluation endpoints after extraction into api/routes/decisions.py.

Covers the real path, not just error codes: draft against a published protocol,
apply, idempotent re-apply, and the stale-context rejection that protects the
operator from writing assessments into a context that no longer exists.

Chromium scenario 06/07 covers the same semantics through the UI; this file keeps
the transport contract under the same guard so a future route move cannot soften
the invariant.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.modules.candidate.models import Candidate, MaterialRevision
from srw.modules.fullworkbench import EvaluationSnapshot, ReevaluationDraft
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

ROOT = Path(__file__).resolve().parents[1]
REEVALUATION_PATHS = {
    ("GET", "/api/v1/candidates/{candidate_id:str}/reevaluations"),
    ("POST", "/api/v1/candidates/{candidate_id:str}/reevaluations"),
    ("POST", "/api/v1/reevaluations/{draft_id:str}/apply"),
}
CRITERION = "experience"


class ReevaluationRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="srw-reevaluation-routes-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.db = root / "reeval.db"
        self.data = root / "data"
        self.knowledge = create_minimal_knowledge_tree(root / "knowledge" / "active")
        engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
        create_v1_schema(engine)
        self.addCleanup(engine.dispose)
        factory = create_v1_session_factory(engine)
        with factory.begin() as session:
            project = Project(title="Synthetic reevaluation", status="open")
            session.add(project)
            session.flush()
            protocol = ProtocolRevision(
                project_id=project.id, revision=1, state="published",
                payload_json=json.dumps({
                    "brief": {"title": "Synthetic role", "summary": ""},
                    "criteria": [{"criterion_key": CRITERION, "name": "Experience",
                                  "decision_critical": True, "verification_required": True}],
                    "assessment_stages": [], "decision_policy": {},
                }, ensure_ascii=False),
                provenance_json="{}", content_hash="p" * 64,
            )
            session.add(protocol)
            session.flush()
            project.current_protocol_revision_id = protocol.id
            candidate = Candidate(project_id=project.id, display_name="Synthetic candidate")
            session.add(candidate)
            session.flush()
            material = MaterialRevision(candidate_id=candidate.id, revision=1,
                                        source_set_hash="m" * 64, provenance_json="{}")
            session.add(material)
            session.flush()
            candidate.current_material_revision_id = material.id
            self.cid = candidate.id
            self.pid = project.id
        self.factory = factory
        self.app = create_v1_app(
            f"sqlite+pysqlite:///{self.db.as_posix()}",
            data_dir=self.data, knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.client = self.enterContext(TestClient(self.app))

    def create_draft(self, **judgment):
        payload = {"summary": "synthetic", "proposal": {"judgments": [
            {"criterion_key": CRITERION, "status": "met", "evidence_level": "strong", **judgment}]}}
        return self.client.post(f"/api/v1/candidates/{self.cid}/reevaluations", json=payload)

    def test_routes_are_owned_by_the_extracted_module(self):
        owners = {}
        for route in self.app.routes:
            for method in getattr(route, "methods", None) or set():
                if (method, route.path) in REEVALUATION_PATHS:
                    owners[(method, route.path)] = route.endpoint.__module__
        self.assertEqual(set(owners), REEVALUATION_PATHS)
        self.assertEqual(set(owners.values()), {"srw.api.routes.decisions"})

    def test_draft_apply_and_idempotent_reapply(self):
        created = self.create_draft()
        self.assertEqual(created.status_code, 200, created.text)
        draft = created.json()
        self.assertEqual(draft["state"], "draft")
        self.assertEqual([c["criterion_key"] for c in draft["diff"]], [CRITERION])

        listed = self.client.get(f"/api/v1/candidates/{self.cid}/reevaluations").json()["drafts"]
        self.assertEqual([row["draft_id"] for row in listed], [draft["draft_id"]])

        applied = self.client.post(f"/api/v1/reevaluations/{draft['draft_id']}/apply")
        self.assertEqual(applied.status_code, 200, applied.text)
        body = applied.json()
        self.assertEqual(body["state"], "applied")
        self.assertEqual(body["applied_changes"], 1)
        self.assertTrue(body["human_decision_unchanged"],
                        "applying an assessment must never record a HumanDecision")

        again = self.client.post(f"/api/v1/reevaluations/{draft['draft_id']}/apply")
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["idempotent"])

        with self.factory() as session:
            snapshots = session.scalars(select(EvaluationSnapshot)).all()
            kinds = sorted(s.snapshot_kind for s in snapshots)
            self.assertEqual(kinds, ["post_reevaluation", "pre_reevaluation"])

    def test_unknown_criterion_key_is_rejected(self):
        response = self.client.post(
            f"/api/v1/candidates/{self.cid}/reevaluations",
            json={"proposal": {"judgments": [{"criterion_key": "not-a-criterion", "status": "met"}]}},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("unknown criterion_key", response.json()["detail"])

    def test_unknown_draft_is_not_found(self):
        self.assertEqual(self.client.post("/api/v1/reevaluations/missing/apply").status_code, 404)

    def test_context_change_makes_the_draft_stale(self):
        draft = self.create_draft().json()
        with self.factory.begin() as session:
            candidate = session.get(Candidate, self.cid)
            replacement = MaterialRevision(candidate_id=self.cid, revision=2,
                                           source_set_hash="n" * 64, provenance_json="{}")
            session.add(replacement)
            session.flush()
            candidate.current_material_revision_id = replacement.id

        stale = self.client.post(f"/api/v1/reevaluations/{draft['draft_id']}/apply")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["state"], "stale")

        with self.factory() as session:
            self.assertEqual(session.get(ReevaluationDraft, draft["draft_id"]).state, "stale")

    def seed_evidence_assessment(self):
        from srw.modules.candidate.models import Source, Claim
        from srw.modules.decision.commands import record_assessment
        with self.factory.begin() as session:
            source = Source(candidate_id=self.cid, source_kind='text', content_hash='s'*64,
                            text_content='Synthetic evidence')
            session.add(source)
            session.flush()
            claims = [Claim(candidate_id=self.cid, source_id=source.id,
                            normalized_text=f'Synthetic claim {i}', claim_hash=str(i)*64)
                      for i in range(2)]
            session.add_all(claims)
            session.flush()
            ids = [c.id for c in claims]
            record_assessment(session, self.cid, CRITERION, status='met', evidence_level='strong',
                              reason='', gap='', claim_ids=[ids[0]], actor='human',
                              evaluation_policy_revision="policy.v1")
        return ids

    def test_evidence_only_change_is_applied_and_snapshots_keep_lineage(self):
        from srw.modules.decision.models import CriterionJudgmentEvidence, HumanDecision
        old, new = self.seed_evidence_assessment()
        created = self.create_draft(claim_ids=[new])
        self.assertEqual(created.status_code, 200, created.text)
        draft = created.json()
        self.assertEqual(len(draft['diff']), 1)
        self.assertEqual(draft['diff'][0]['before']['claim_ids'], [old])
        response = self.client.post(f"/api/v1/reevaluations/{draft['draft_id']}/apply")
        self.assertEqual(response.status_code, 200, response.text)
        with self.factory() as session:
            self.assertEqual(list(session.scalars(select(CriterionJudgmentEvidence.claim_id))), [new])
            snapshots = {s.snapshot_kind: json.loads(s.payload_json)['judgments'][0]['claim_ids']
                         for s in session.scalars(select(EvaluationSnapshot))}
            self.assertEqual(snapshots, {'pre_reevaluation': [old], 'post_reevaluation': [new]})
            self.assertEqual(list(session.scalars(select(HumanDecision))), [])
        again = self.client.post(f"/api/v1/reevaluations/{draft['draft_id']}/apply")
        self.assertTrue(again.json()['idempotent'])

    def test_duplicate_claim_references_are_not_a_change(self):
        old, _ = self.seed_evidence_assessment()
        response = self.create_draft(claim_ids=[old, old])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['diff'], [])

    def test_removing_evidence_is_an_explicit_change(self):
        from srw.modules.decision.models import CriterionJudgmentEvidence
        self.seed_evidence_assessment()
        draft = self.create_draft(claim_ids=[]).json()
        self.assertEqual(len(draft['diff']), 1)
        response = self.client.post(f"/api/v1/reevaluations/{draft['draft_id']}/apply")
        self.assertEqual(response.status_code, 200, response.text)
        with self.factory() as session:
            self.assertEqual(list(session.scalars(select(CriterionJudgmentEvidence))), [])

    def test_invalid_evidence_apply_rolls_back_snapshots_and_assessment(self):
        from srw.modules.decision.models import CriterionJudgmentEvidence
        old, _ = self.seed_evidence_assessment()
        draft = self.create_draft(claim_ids=['nonexistent-claim']).json()
        response = self.client.post(f"/api/v1/reevaluations/{draft['draft_id']}/apply")
        self.assertEqual(response.status_code, 404, response.text)
        with self.factory() as session:
            self.assertEqual(list(session.scalars(select(CriterionJudgmentEvidence.claim_id))), [old])
            self.assertEqual(list(session.scalars(select(EvaluationSnapshot))), [])
            self.assertEqual(session.get(ReevaluationDraft, draft['draft_id']).state, 'draft')


    def test_omitted_evidence_keeps_legacy_unchanged_proposal_noop(self):
        self.seed_evidence_assessment()
        response = self.create_draft()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['diff'], [])


if __name__ == "__main__":
    unittest.main()
