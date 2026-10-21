"""Knowledge-search results become protocol criteria through the governance domain service.

Covers the extracted apply_result_as_criterion orchestration and the thin HTTP adapter.
Synthetic SQLite workspace only; no knowledge DB files and no network are touched.
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
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.knowledge_governance.service import apply_result_as_criterion
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

_DRAFT_PAYLOAD = {
    "brief": {"title": "Synthetic role", "summary": ""},
    "recruitment_context": {"role_title": "Synthetic role", "location": "北京"},
    "criteria": [],
    "assessment_stages": [],
    "decision_policy": {"human_final": True},
}


def _result(**overrides):
    base = {
        "database": "competency",
        "knowledge_id": "competency:competency_fts:c-1",
        "title": "结构化面试能力",
        "detail": "行为面试与评分一致性",
    }
    base.update(overrides)
    return base


class KnowledgeApplyCriterionDomainTests(unittest.TestCase):
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

    def _drafts(self, session):
        return session.scalars(
            select(ProtocolRevision).where(
                ProtocolRevision.project_id == self.pid, ProtocolRevision.state == "draft"
            )
        ).all()

    def test_apply_appends_criterion_with_knowledge_provenance(self):
        with self.factory.begin() as session:
            revision_id, criterion = apply_result_as_criterion(session, project_id=self.pid, result=_result())
            payload = ProtocolRepository(session).get_payload(revision_id)
        self.assertEqual(len(payload["criteria"]), 1)
        self.assertEqual(criterion["name"], "结构化面试能力")
        self.assertEqual(criterion["definition"], "行为面试与评分一致性")
        self.assertFalse(criterion["decision_critical"])
        self.assertTrue(criterion["verification_required"])
        self.assertEqual(criterion["verification_probes"], [])
        self.assertEqual(criterion["knowledge_source"]["knowledge_id"], "competency:competency_fts:c-1")
        self.assertEqual(criterion["knowledge_source"]["database"], "competency")
        self.assertEqual(payload["criteria"][-1], criterion)

    def test_apply_forks_draft_when_none_exists(self):
        with self.factory.begin() as session:
            revision_id, _ = apply_result_as_criterion(session, project_id=self.pid, result=_result())
            drafts = self._drafts(session)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].id, revision_id)

    def test_apply_appends_to_existing_draft_without_duplicating(self):
        with self.factory.begin() as session:
            first_id, _ = apply_result_as_criterion(session, project_id=self.pid, result=_result(title="第一条"))
            second_id, _ = apply_result_as_criterion(session, project_id=self.pid, result=_result(title="第二条"))
            payload = ProtocolRepository(session).get_payload(second_id)
            drafts = self._drafts(session)
        self.assertEqual(first_id, second_id)
        self.assertEqual(len(drafts), 1)
        self.assertEqual([c["name"] for c in payload["criteria"]], ["第一条", "第二条"])

    def test_apply_unknown_project_is_not_found(self):
        with self.factory() as session:
            with self.assertRaises(V1NotFoundError):
                apply_result_as_criterion(session, project_id="no-such-project", result=_result())

    def test_criterion_name_override_and_fallbacks(self):
        with self.factory.begin() as session:
            _, overridden = apply_result_as_criterion(
                session, project_id=self.pid, result=_result(), criterion_name="  人工命名  "
            )
            self.assertEqual(overridden["name"], "人工命名")
        with self.factory.begin() as session:
            _, fallback = apply_result_as_criterion(session, project_id=self.pid, result=_result(title=""))
            self.assertEqual(fallback["name"], "知识建议")

    def test_flags_and_provenance_pass_through(self):
        with self.factory.begin() as session:
            revision_id, criterion = apply_result_as_criterion(
                session,
                project_id=self.pid,
                result=_result(),
                criterion_name="关键项",
                decision_critical=True,
                verification_required=False,
            )
            row = session.get(ProtocolRevision, revision_id)
            provenance = json.loads(row.provenance_json or "{}")
        self.assertTrue(criterion["decision_critical"])
        self.assertFalse(criterion["verification_required"])
        self.assertEqual(provenance["origin"], "knowledge_apply")
        self.assertEqual(provenance["knowledge_id"], "competency:competency_fts:c-1")

    def test_non_dict_result_is_rejected(self):
        with self.factory() as session:
            with self.assertRaises(V1InvariantError):
                apply_result_as_criterion(session, project_id=self.pid, result=["not", "a", "dict"])


class KnowledgeApplyHttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.url = f"sqlite+pysqlite:///{(self.root / 'synthetic.db').as_posix()}"
        engine = create_v1_engine(self.url)
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
        app = create_v1_app(
            self.url,
            data_dir=self.root / "data",
            knowledge_dir=create_minimal_knowledge_tree(self.root / "knowledge" / "active"),
        )
        self.client = self.enterContext(TestClient(app))

    def _persisted_criterion_names(self):
        engine = create_v1_engine(self.url)
        try:
            factory = create_v1_session_factory(engine)
            with factory() as session:
                drafts = session.scalars(
                    select(ProtocolRevision).where(
                        ProtocolRevision.project_id == self.pid, ProtocolRevision.state == "draft"
                    )
                ).all()
                names = []
                for draft in drafts:
                    names.extend(c["name"] for c in ProtocolRepository(session).get_payload(draft.id)["criteria"])
                return names
        finally:
            engine.dispose()

    def test_apply_route_persists_criterion(self):
        response = self.client.post(
            f"/api/v1/projects/{self.pid}/knowledge/apply",
            json={"result": _result(), "criterion_name": "沟通能力"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["criterion"]["name"], "沟通能力")
        self.assertEqual(body["criterion"]["knowledge_source"]["database"], "competency")
        self.assertIn("沟通能力", self._persisted_criterion_names())

    def test_apply_route_rejects_non_dict_result(self):
        response = self.client.post(f"/api/v1/projects/{self.pid}/knowledge/apply", json={"result": "nope"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["code"], "invariant_conflict")

    def test_apply_route_unknown_project_is_404(self):
        response = self.client.post("/api/v1/projects/no-such-project/knowledge/apply", json={"result": _result()})
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
