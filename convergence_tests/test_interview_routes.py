"""Focused HTTP regressions for the extracted interview route adapter."""
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
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory


class InterviewRouteExtractionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="srw-interview-route-"); self.addCleanup(tmp.cleanup)
        root=Path(tmp.name); url=f"sqlite+pysqlite:///{(root/'synthetic.db').as_posix()}"
        self.engine=create_v1_engine(url); self.addCleanup(self.engine.dispose); create_v1_schema(self.engine)
        self.factory=create_v1_session_factory(self.engine)
        with self.factory.begin() as s:
            p=Project(title="Synthetic interview route"); s.add(p); s.flush()
            c=Candidate(project_id=p.id,display_name="Synthetic person"); s.add(c); s.flush(); self.cid=c.id
        app=create_v1_app(url,data_dir=root/'data',knowledge_dir=create_minimal_knowledge_tree(root/'knowledge'/'active'),frontend_dist=Path(__file__).resolve().parents[1]/'frontend'/'dist')
        self.client=self.enterContext(TestClient(app))
        created=self.client.post(f"/api/v1/candidates/{self.cid}/events",json={"event_type":"interview","event_state":"completed","title":"Synthetic interview"})
        self.assertEqual(created.status_code,200,created.text); self.event_id=created.json()['event_id']

    def test_independent_scorecards_remain_locked_after_submit_and_keep_disagreement(self):
        def submit(evaluator,rating):
            return self.client.post(f"/api/v1/events/{self.event_id}/scorecards",json={"evaluator":evaluator,"feedback":[{"criterion_key":"synthetic","rating":rating}],"recommendation":rating,"submit":True})
        a=submit('evaluator-a','strong'); b=submit('evaluator-b','concern')
        self.assertEqual(a.status_code,200,a.text); self.assertEqual(b.status_code,200,b.text)
        locked=submit('evaluator-a','acceptable')
        self.assertEqual(locked.status_code,409,locked.text)
        view=self.client.get(f"/api/v1/events/{self.event_id}/scorecards")
        self.assertEqual(view.status_code,200,view.text)
        self.assertEqual(len(view.json()['scorecards']),2)
        self.assertTrue(view.json()['criteria']['synthetic']['disagreement'])
        with self.factory() as s:
            events=list(s.scalars(select(AuditEvent).where(AuditEvent.entity_type=='interview_scorecard').order_by(AuditEvent.created_at)).all())
            self.assertEqual([e.event_type for e in events],["INTERVIEW_SCORECARD_SUBMITTED","INTERVIEW_SCORECARD_SUBMITTED"])
            self.assertEqual([e.actor for e in events],["evaluator-a","evaluator-b"])


if __name__=='__main__': unittest.main()
