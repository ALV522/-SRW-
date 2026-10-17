import json, shutil, sqlite3, tempfile, unittest
from pathlib import Path
from sqlalchemy import inspect, select
from srw.modules.protocol.models import Project
from srw.modules.protocol.repository import ProtocolRepository
from srw.modules.planning.service import upsert_plan
from srw.modules.recruitment_intelligence.models import SourcingChannelObservation
from srw.modules.recruitment_intelligence.service import record_observation,intelligence_snapshot
from srw.modules.knowledge_packages.service import ControlledKnowledgePackages
from srw.runtime.db.schema import V1_SCHEMA_REVISION,V1SchemaMeta,create_v1_schema
from srw.runtime.db.session import create_v1_engine,create_v1_session_factory
from knowledge_fixture import create_minimal_knowledge_tree

ROOT=Path(__file__).resolve().parents[1]
class Convergence06Test(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.knowledge=create_minimal_knowledge_tree(self.root/'knowledge'/'active');self.db=self.root/'test.db';self.engine=create_v1_engine(f'sqlite+pysqlite:///{self.db}');create_v1_schema(self.engine);self.factory=create_v1_session_factory(self.engine)
 def tearDown(self):self.engine.dispose();self.tmp.cleanup()
 def _project(self,s):
  p=Project(title='招聘',status='open');s.add(p);s.flush();repo=ProtocolRepository(s);d=repo.create_draft(p.id,{'brief':{'title':'招聘','summary':''},'recruitment_context':{'role_title':'招聘','location':'北京'},'criteria':[],'assessment_stages':[],'decision_policy':{'human_final':True}});repo.publish(d.id);return p
 def test_sourcing_channel_observation_validates_funnel_and_separates_intelligence_from_hiring_rank(self):
  with self.factory() as s:
   p=self._project(s);upsert_plan(s,p.id,target_hires=2,target_date='2026-12-01',owner='TA',source_channels=['内推','招聘网站'],notes='')
   record_observation(s,p.id,channel='内推',period='2026Q4',sourced=20,contacted=16,screened=10,interviewed=6,offered=2,hired=1,spend_cny=1000,human_confirmed=True,provenance='ATS export + human confirm',notes='')
   snap=intelligence_snapshot(s,p.id,knowledge_dir=self.knowledge,role_title='招聘',location='北京')
   self.assertEqual(snap['channels'][0]['channel'],'内推');self.assertEqual(snap['channels'][0]['hire_rate_from_sourced'],0.05);self.assertIn('招聘网站',snap['measurement_gaps']);self.assertTrue(snap['semantics']['channel_efficiency_is_not_candidate_rank']);self.assertTrue(snap['semantics']['market_signal_is_not_candidate_score'])
   with self.assertRaises(Exception):record_observation(s,p.id,channel='bad',period='',sourced=1,contacted=2,screened=0,interviewed=0,offered=0,hired=0,spend_cny=0,human_confirmed=False,provenance='manual',notes='')
 def test_controlled_knowledge_apply_is_two_phase_digest_guarded_and_rollback_exact(self):
  active=self.root/'knowledge-copy'/'active';shutil.copytree(self.knowledge/'taxonomy',active/'taxonomy');mgr=ControlledKnowledgePackages(data_dir=self.root/'data',active_dir=active)
  taxonomy=active/'taxonomy'/'knowledge.db';before=taxonomy.read_bytes()
  con=sqlite3.connect(taxonomy);target=con.execute("SELECT role_id FROM canonical_role ORDER BY role_id LIMIT 1").fetchone()[0];con.close()
  manifest=mgr.prepare_taxonomy_alias(proposal_id='p-test',source_title='Convergence Test Alias 9917',target_id=target,target_type='role',reviewer='KM',reason='test')
  self.assertFalse(manifest['active_knowledge_mutated']);self.assertGreaterEqual(manifest['semantic_diff']['totals']['added'],2);self.assertEqual(taxonomy.read_bytes(),before)
  with self.assertRaises(Exception):mgr.activate('curation-p-test',expected_digest='wrong',actor='KM')
  applied=mgr.activate('curation-p-test',expected_digest=manifest['activation_requires_explicit_digest'],actor='KM');self.assertEqual(applied['status'],'active');self.assertNotEqual(taxonomy.read_bytes(),before)
  con=sqlite3.connect(taxonomy);self.assertEqual(con.execute("SELECT COUNT(*) FROM title_alias WHERE title=?",('Convergence Test Alias 9917',)).fetchone()[0],1);con.close()
  rolled=mgr.rollback(actor='KM');self.assertEqual(rolled['status'],'rolled_back');self.assertEqual(taxonomy.read_bytes(),before)
 def test_0013_database_upgrades_to_0014_and_registers_intelligence_table(self):
  old=self.root/'old.db';con=sqlite3.connect(old);con.execute('CREATE TABLE v1_schema_meta (schema_revision VARCHAR(40) PRIMARY KEY NOT NULL, created_at DATETIME NOT NULL)');con.execute("INSERT INTO v1_schema_meta VALUES ('v1_0013','2026-10-16')");con.commit();con.close();engine=create_v1_engine(f'sqlite+pysqlite:///{old}')
  try:
   create_v1_schema(engine);self.assertIn('sourcing_channel_observation',set(inspect(engine).get_table_names()));factory=create_v1_session_factory(engine)
   with factory() as s:self.assertEqual(s.scalar(select(V1SchemaMeta).limit(1)).schema_revision,V1_SCHEMA_REVISION)
  finally:engine.dispose()
if __name__=='__main__':unittest.main()
