import json, sqlite3, tempfile, unittest
from pathlib import Path
from sqlalchemy import inspect, select
from srw.kernel.hashing import content_hash
from srw.modules.candidate.models import Candidate, Source
from srw.modules.candidate.repository import MaterialRepository
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.feedback.models import FeedbackRecord
from srw.modules.feedback.service import classify_feedback, create_feedback, review_feedback
from srw.modules.decision_operations.models import DecisionAction, KnowledgeFeedbackDraft
from srw.modules.decision_operations.service import recommend_actions, transition_action, stage_knowledge_feedback
from srw.modules.planning.models import RecruitmentPlan
from srw.modules.planning.service import upsert_plan, planning_snapshot
from srw.modules.knowledge_governance.models import KnowledgeCurationProposal
from srw.modules.knowledge_governance.service import create_from_feedback, review_proposal, export_proposal
from srw.runtime.db.schema import V1_SCHEMA_REVISION, V1SchemaMeta, create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory

class Convergence05Test(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.db'
        self.engine=create_v1_engine(f'sqlite+pysqlite:///{self.db}');create_v1_schema(self.engine);self.factory=create_v1_session_factory(self.engine)
    def tearDown(self):self.engine.dispose();self.tmp.cleanup()
    def _project(self,s):
        p=Project(title='Recruiting Analyst',status='open');s.add(p);s.flush();repo=ProtocolRepository(s)
        d=repo.create_draft(p.id,{'brief':{'title':'Recruiting Analyst','summary':''},'criteria':[{'criterion_key':'exp','name':'Experience','weight':1,'decision_critical':True,'verification_required':True}],'assessment_stages':[],'decision_policy':{'human_final':True}});repo.publish(d.id);return p
    def _candidate(self,s,p,name='Candidate'):
        c=Candidate(project_id=p.id,display_name=name);s.add(c);s.flush();text='Two years recruiting experience';src=Source(candidate_id=c.id,source_kind='resume',content_hash=content_hash(text),media_type='text/plain',text_content=text,metadata_json='{}');s.add(src);s.flush();MaterialRepository(s).publish_revision(c.id,[src.id],{'test':True});return c
    def test_feedback_classification_and_human_apply_creates_new_material_revision(self):
        cls=classify_feedback('候选人事实：补充有 ATS 实施经验\n岗位需求：新增英语要求\n冲突：任职年限口径不一致')
        self.assertEqual(cls['feedback_type'],'mixed');self.assertEqual(len(cls['candidate_facts']),1);self.assertEqual(len(cls['job_requirements']),1);self.assertEqual(len(cls['conflicts']),1);self.assertEqual(len(cls['follow_up_questions']),3);self.assertEqual(cls['follow_up_questions'][0]['reason'],'conflict')
        with self.factory() as s:
            p=self._project(s);c=self._candidate(s,p);old=c.current_material_revision_id
            fb=create_feedback(s,project_id=p.id,candidate_id=c.id,text='候选人事实：补充有 ATS 实施经验\n岗位需求：新增英语要求',actor='TA')
            review_feedback(s,fb.id,action='apply_candidate_facts',reviewer='TA2',reason='电话核实',evaluation_policy_revision='policy.v1')
            s.flush();self.assertEqual(fb.status,'applied');self.assertNotEqual(c.current_material_revision_id,old);self.assertIsNotNone(fb.applied_source_id)
            # Job requirement is classified for protocol review but never silently mutates the published protocol.
            self.assertEqual(json.loads(fb.classification_json)['job_requirements'],['新增英语要求'])
    def test_decision_action_lifecycle_requires_human_completion_and_stages_learning(self):
        with self.factory() as s:
            p=self._project(s);c=self._candidate(s,p)
            rows=recommend_actions(s,p.id,'policy.v1');self.assertEqual(len(rows),1);a=rows[0];self.assertEqual(a.action_type,'phone_verify');self.assertEqual(a.status,'proposed')
            # Idempotent recommendation.
            again=recommend_actions(s,p.id,'policy.v1');self.assertEqual(again[0].id,a.id)
            transition_action(s,a.id,transition='accept',actor='TA',expected_state_version=a.expected_state_version,reason='take ownership')
            with self.assertRaises(Exception):transition_action(s,a.id,transition='complete',actor='TA',expected_state_version=a.expected_state_version,outcome={'human_confirmed':False})
            outcome={'human_confirmed':True,'result':'verified','knowledge_feedback':{'feedback_type':'verification_pattern','title':'核实经验','summary':'电话核实比简历表述更可靠','evidence_refs':['call-note-1']}}
            transition_action(s,a.id,transition='complete',actor='TA',expected_state_version=a.expected_state_version,outcome=outcome)
            k=stage_knowledge_feedback(s,a.id,actor='TA');self.assertEqual(k.status,'draft')
            k2=stage_knowledge_feedback(s,a.id,actor='TA');self.assertEqual(k2.id,k.id)
            proposal=create_from_feedback(s,k.id,actor='KM');self.assertEqual(proposal.status,'draft');self.assertEqual(k.status,'promoted_to_curation')
            review_proposal(s,proposal.id,action='keep_unknown',reviewer='KM2',reason='样本不足',expected_state_version=proposal.expected_state_version);self.assertEqual(proposal.status,'reviewed')
            exported,path=export_proposal(s,proposal.id,actor='KM2',export_root=Path(self.tmp.name)/'exports');self.assertEqual(exported.status,'exported');data=json.loads(path.read_text(encoding='utf-8'));self.assertFalse(data['active_knowledge_mutated'])
    def test_recruitment_plan_is_persistent_and_separates_operations_from_hiring_rank(self):
        with self.factory() as s:
            p=self._project(s);self._candidate(s,p,'A');self._candidate(s,p,'B')
            upsert_plan(s,p.id,target_hires=2,target_date='2026-11-30',owner='TA Lead',source_channels=['校园招聘','内推'],notes='priority role')
            recommend_actions(s,p.id,'policy.v1')
            snap=planning_snapshot(s,p.id,'policy.v1');self.assertTrue(snap['plan']['configured']);self.assertEqual(snap['plan']['target_hires'],2);self.assertEqual(snap['remaining_hires'],2);self.assertEqual(snap['open_actions']['by_type']['phone_verify'],2);self.assertTrue(snap['semantics']['operational_priority_is_not_hiring_rank']);self.assertTrue(snap['semantics']['missing_is_not_zero'])
    def test_protocol_change_marks_old_open_action_stale_and_creates_new_context_action(self):
        with self.factory() as s:
            p=self._project(s);self._candidate(s,p);old=recommend_actions(s,p.id,'policy.v1')[0]
            repo=ProtocolRepository(s);d=repo.fork_current_to_draft(p.id);payload=json.loads(d.payload_json);payload['criteria'][0]['name']='Updated Experience';repo.update_draft(d.id,payload,{'test':True});repo.publish(d.id)
            new=recommend_actions(s,p.id,'policy.v1');self.assertEqual(old.status,'stale');self.assertEqual(len(new),1);self.assertNotEqual(new[0].id,old.id);self.assertNotEqual(new[0].decision_context_hash,old.decision_context_hash)
    def test_0012_database_upgrades_to_0013_and_registers_recovered_tables(self):
        old=Path(self.tmp.name)/'old0012.db';conn=sqlite3.connect(old)
        try:
            conn.execute('CREATE TABLE v1_schema_meta (schema_revision VARCHAR(40) PRIMARY KEY NOT NULL, created_at DATETIME NOT NULL)');conn.execute("INSERT INTO v1_schema_meta VALUES ('v1_0012','2026-10-16 00:00:00')");conn.commit()
        finally:conn.close()
        engine=create_v1_engine(f'sqlite+pysqlite:///{old}')
        try:
            create_v1_schema(engine);tables=set(inspect(engine).get_table_names())
            for name in {'feedback_record','decision_action','knowledge_feedback_draft','recruitment_plan','knowledge_curation_proposal'}:self.assertIn(name,tables)
            factory=create_v1_session_factory(engine)
            with factory() as s:self.assertEqual(s.scalar(select(V1SchemaMeta).limit(1)).schema_revision,V1_SCHEMA_REVISION)
        finally:engine.dispose()

if __name__=='__main__':unittest.main()
