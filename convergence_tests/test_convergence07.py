import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from srw.api.app import create_v1_app
from srw.modules.recruitment_intelligence.importer import preview_csv
from knowledge_fixture import create_minimal_knowledge_tree

ROOT = Path(__file__).resolve().parents[1]


class Convergence07Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.knowledge = create_minimal_knowledge_tree(self.root/'knowledge'/'active')

    def tearDown(self):
        self.tmp.cleanup()

    def _app(self):
        return create_v1_app(
            f"sqlite+pysqlite:///{(self.root/'test.db').as_posix()}",
            data_dir=self.root/'data',
            knowledge_dir=self.knowledge,
            frontend_dist=ROOT/'frontend'/'dist',
        )

    def test_windows_host_runtime_abi_matches_inherited_08_host_contract(self):
        env = {
            'RECRUITMENT_INSTANCE_ID':'host-instance-07',
            'RECRUITMENT_SESSION_ID':'host-session-07',
            'RECRUITMENT_SESSION_TOKEN':'host-secret-07',
            'RECRUITMENT_RELEASE_ID':(ROOT/'VERSION').read_text(encoding='utf-8').strip(),
            'RECRUITMENT_RUNTIME_MODE':'desktop',
            'RECRUITMENT_EDITION':'windows',
        }
        with patch.dict(os.environ, env, clear=False):
            app=self._app(); called=[]; app.state.shutdown_callback=lambda:called.append(True)
            with TestClient(app) as client:
                ready=client.get('/api/v1/runtime/ready'); info=client.get('/api/v1/runtime/info')
                self.assertEqual(ready.status_code,200); self.assertEqual(ready.json()['status'],'ready')
                payload=info.json(); self.assertEqual(payload['runtime'],'desktop'); self.assertEqual(payload['edition'],'windows')
                self.assertEqual(payload['instanceId'],'host-instance-07'); self.assertEqual(payload['sessionId'],'host-session-07')
                self.assertEqual(payload['releaseId'],(ROOT/'VERSION').read_text(encoding='utf-8').strip())
                self.assertEqual(client.get('/').status_code,200)
                self.assertEqual(client.post('/api/v1/runtime/shutdown').status_code,403)
                self.assertEqual(client.post('/api/v1/runtime/shutdown',headers={'X-SRW-Session':'wrong'}).status_code,403)
                self.assertEqual(client.post('/api/v1/runtime/shutdown',headers={'X-SRW-Session':'host-secret-07'}).status_code,202)
            self.assertEqual(called,[True])

    def test_csv_import_preview_supports_chinese_headers_and_digest_guard(self):
        csv_text='渠道,期间,候选人数,已联系,已筛选,已面试,Offer数,录用数,渠道成本,人工确认\n内推,2026Q4,20,16,10,6,2,1,1000,是\n招聘网站,2026Q4,40,30,20,10,3,1,5000,否\n'
        p=preview_csv(csv_text)
        self.assertTrue(p['can_commit']); self.assertEqual(p['row_count'],2); self.assertEqual(p['rows'][0]['channel'],'内推')
        self.assertTrue(p['rows'][0]['human_confirmed']); self.assertFalse(p['rows'][1]['human_confirmed'])
        self.assertEqual(len(p['digest']),64); self.assertTrue(p['semantics']['import_does_not_rank_candidates'])

    def test_csv_import_preview_blocks_invalid_funnel(self):
        csv_text='channel,sourced,contacted,screened,interviewed,offered,hired\nbad,1,2,1,0,0,0\n'
        p=preview_csv(csv_text)
        self.assertFalse(p['can_commit']); self.assertEqual(p['error_count'],1)

    def test_csv_import_http_preview_commit_is_atomic_and_advisory_by_default(self):
        app=self._app()
        with TestClient(app) as client:
            created=client.post('/api/v1/projects',json={'title':'工程师招聘','role_title':'工程师','brief_summary':''})
            self.assertEqual(created.status_code,200,created.text)
            project_id=created.json()['project']['id'] if 'project' in created.json() else created.json()['project_id']
            content='channel,period,sourced,contacted,screened,interviewed,offered,hired,spend_cny\n内推,2026Q4,20,15,10,5,2,1,1200\n'
            preview=client.post(f'/api/v1/projects/{project_id}/sourcing-observations/import-preview',json={'content':content})
            self.assertEqual(preview.status_code,200,preview.text); digest=preview.json()['digest']
            bad=client.post(f'/api/v1/projects/{project_id}/sourcing-observations/import-commit',json={'content':content+'\n','expected_digest':digest,'filename':'ats.csv'})
            self.assertEqual(bad.status_code,409)
            commit=client.post(f'/api/v1/projects/{project_id}/sourcing-observations/import-commit',json={'content':content,'expected_digest':digest,'filename':'ats.csv'})
            self.assertEqual(commit.status_code,200,commit.text); self.assertEqual(commit.json()['imported_count'],1)
            rows=client.get(f'/api/v1/projects/{project_id}/sourcing-observations').json()['observations']
            self.assertEqual(len(rows),1); self.assertFalse(rows[0]['human_confirmed']); self.assertIn('csv_import:ats.csv',rows[0]['provenance'])

    def test_inherited_wpf_host_source_and_current_backend_share_the_same_abi(self):
        host=(ROOT/'desktop'/'SRW.Desktop')
        app_paths=(host/'Runtime'/'AppPaths.cs').read_text(encoding='utf-8')
        backend=(host/'Hosting'/'BackendProcess.cs').read_text(encoding='utf-8')
        client=(host/'Runtime'/'RuntimeApiClient.cs').read_text(encoding='utf-8')
        main=(host/'MainWindow.xaml.cs').read_text(encoding='utf-8')
        self.assertIn('scripts", "run_local.py',app_paths)
        self.assertIn('--edition windows --workspace-lock host',backend)
        self.assertIn('/api/v1/runtime/ready',client); self.assertIn('/api/v1/runtime/info',client); self.assertIn('/api/v1/runtime/shutdown',client)
        self.assertIn('X-SRW-Session',client); self.assertIn('Browser.Source = _controller.ApplicationUri',main)
        current=(ROOT/'scripts'/'run_local.py').read_text(encoding='utf-8')
        self.assertIn('--workspace-lock',current); self.assertTrue((ROOT/'VERSION').is_file()); self.assertTrue((ROOT/'BUILD_INFO.json').is_file())

    def test_native_assembler_requires_exact_v088_carrier_and_never_claims_gui_acceptance(self):
        ps=(ROOT/'scripts'/'build_windows_native_from_v088.ps1').read_text(encoding='utf-8')
        self.assertIn('f12933a1f6639168911af3788d207ced521be8a50841d7d39e7a2169eed3d5ab',ps)
        self.assertIn('DOTNET_BUILD_TRUTH.json',ps); self.assertIn('executable_sha256',ps)
        self.assertIn('Exact Windows GUI smoke remains required',ps)


if __name__=='__main__': unittest.main()
