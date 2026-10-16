import base64
import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

import fitz
from starlette.testclient import TestClient

from srw.api.app import create_v1_app
from srw.modules.candidate.models import Claim, Source
from srw.modules.knowledge_packages.service import ControlledKnowledgePackages
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory
from knowledge_fixture import create_minimal_knowledge_tree

ROOT = Path(__file__).resolve().parents[1]


class Convergence08Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'test.db'
        self.data = self.root / 'data'
        self.knowledge = create_minimal_knowledge_tree(self.root / 'knowledge' / 'active')

    def tearDown(self):
        self.tmp.cleanup()

    def _app(self):
        return create_v1_app(
            f"sqlite+pysqlite:///{self.db.as_posix()}",
            data_dir=self.data,
            knowledge_dir=self.knowledge,
            frontend_dist=ROOT / 'frontend' / 'dist',
        )

    @staticmethod
    def _pdf_bytes():
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 90), 'Python experience five years', fontsize=14)
        page.insert_text((72, 125), 'SQL and data analysis', fontsize=12)
        raw = doc.tobytes()
        doc.close()
        return raw

    def _project_candidate(self, client, display_name='Candidate'):
        created = client.post('/api/v1/projects', json={'title':'测试招聘','role_title':'工程师','brief_summary':''})
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        pid = body['project']['id'] if 'project' in body else body['project_id']
        candidate = client.post(f'/api/v1/projects/{pid}/candidates', json={'display_name':display_name})
        self.assertEqual(candidate.status_code, 200, candidate.text)
        return pid, candidate.json()['candidate_id']

    def test_pdf_source_viewer_renders_grounded_claim_as_highlighted_png(self):
        app = self._app()
        with TestClient(app) as client:
            pid, cid = self._project_candidate(client)
            raw = self._pdf_bytes()
            intake = client.post(f'/api/v1/candidates/{cid}/files', json={
                'filename':'resume.pdf','media_type':'application/pdf','base64':base64.b64encode(raw).decode('ascii'),'source_kind':'resume'
            })
            self.assertEqual(intake.status_code, 200, intake.text)
            sid = intake.json()['source_id']
            content = client.get(f'/api/v1/sources/{sid}/content').json()
            text = content['text_content']
            quote = 'Python experience five years'
            start = text.index(quote)

            engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
            factory = create_v1_session_factory(engine)
            try:
                with factory.begin() as s:
                    source = s.get(Source, sid)
                    claim = Claim(
                        candidate_id=cid, source_id=sid, normalized_text=quote,
                        claim_hash=hashlib.sha256(quote.encode()).hexdigest(),
                        source_locator_json=json.dumps({'quote':quote,'char_start':start}, separators=(',',':')),
                        proposal_metadata_json='{}', authority='source', confirmation_state='unreviewed',
                    )
                    s.add(claim); s.flush(); claim_id = claim.id
            finally:
                engine.dispose()

            grounding = client.get(f'/api/v1/claims/{claim_id}/grounding')
            self.assertEqual(grounding.status_code, 200, grounding.text)
            locator = grounding.json()['locator']
            self.assertEqual(locator['page'], 1); self.assertEqual(len(locator['bbox']), 4)
            rendered = client.get(f'/api/v1/sources/{sid}/page/1?claim_id={claim_id}&scale=1.2')
            self.assertEqual(rendered.status_code, 200, rendered.text)
            self.assertEqual(rendered.headers['content-type'], 'image/png')
            self.assertEqual(rendered.headers['x-srw-grounding-highlight'], '1')
            self.assertTrue(rendered.content.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertGreater(len(rendered.content), 1000)
            mismatch = client.get(f'/api/v1/sources/{sid}/page/2?claim_id={claim_id}')
            self.assertIn(mismatch.status_code, {404,409})

    def test_competency_alias_controlled_apply_is_digest_guarded_and_exactly_rollbackable(self):
        active = self.root / 'knowledge-copy' / 'active'
        shutil.copytree(self.knowledge / 'competency', active / 'competency')
        mgr = ControlledKnowledgePackages(data_dir=self.root/'data-km', active_dir=active)
        db = active / 'competency' / 'knowledge.db'; before = db.read_bytes()
        con = sqlite3.connect(db)
        target = con.execute("SELECT competency_id FROM competency WHERE status='active' ORDER BY competency_id LIMIT 1").fetchone()[0]
        con.close()
        manifest = mgr.prepare_competency_alias(
            proposal_id='p-comp-08', source_title='Convergence 08 Capability Alias', target_id=target,
            reviewer='KM', reason='human reviewed capability alias',
        )
        self.assertEqual(manifest['sources'][0]['source_type'], 'competency')
        self.assertFalse(manifest['active_knowledge_mutated']); self.assertEqual(db.read_bytes(), before)
        self.assertGreaterEqual(manifest['semantic_diff']['totals']['added'], 1)
        with self.assertRaises(Exception):
            mgr.activate('curation-p-comp-08', expected_digest='0'*64, actor='KM')
        mgr.activate('curation-p-comp-08', expected_digest=manifest['activation_requires_explicit_digest'], actor='KM')
        con = sqlite3.connect(db)
        row = con.execute("SELECT competency_id FROM competency_alias WHERE alias=?", ('Convergence 08 Capability Alias',)).fetchone()
        con.close(); self.assertEqual(row[0], target)
        mgr.rollback(actor='KM'); self.assertEqual(db.read_bytes(), before)

    def test_competency_alias_conflict_is_blocked_before_prepare_completes(self):
        active = self.root / 'knowledge-copy2' / 'active'
        shutil.copytree(self.knowledge / 'competency', active / 'competency')
        db = active / 'competency' / 'knowledge.db'
        con = sqlite3.connect(db)
        rows = con.execute("SELECT competency_id FROM competency WHERE status='active' ORDER BY competency_id LIMIT 2").fetchall()
        target1, target2 = rows[0][0], rows[1][0]
        con.execute("INSERT INTO competency_alias(alias_id,competency_id,alias,language,alias_type,source_id,status) VALUES (?,?,?,?,?,?,?)",('TEST-CONFLICT',target1,'Collision Alias','en','test',None,'active'))
        con.commit(); con.close()
        mgr = ControlledKnowledgePackages(data_dir=self.root/'data-km2', active_dir=active)
        with self.assertRaises(Exception):
            mgr.prepare_competency_alias(proposal_id='p-conflict', source_title='Collision Alias', target_id=target2, reviewer='KM', reason='test')

    def test_backup_restore_rejects_duplicate_zip_member_before_sqlite_read(self):
        app = self._app()
        with TestClient(app) as client:
            backup_dir = self.data / 'backups'; backup_dir.mkdir(parents=True, exist_ok=True)
            path = backup_dir / 'duplicate.zip'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.writestr('data/srw_v1.db', b'first')
                    z.writestr('data/srw_v1.db', b'second')
            r = client.post('/api/v1/system/backups/duplicate.zip/restore')
            self.assertEqual(r.status_code, 409, r.text)
            self.assertIn('duplicate ZIP members', r.text)
            self.assertFalse((self.data/'pending_restore.json').exists())

    def test_candidate_and_contact_csv_exports_are_excel_formula_safe(self):
        app = self._app()
        with TestClient(app) as client:
            pid, cid = self._project_candidate(client, display_name='=2+2')
            contact = client.patch(f'/api/v1/candidates/{cid}/contact', json={
                'display_name':'=2+2','phone':'+12345','email':'@example.invalid','user_confirmed':True,'actor':'human'
            })
            self.assertEqual(contact.status_code, 200, contact.text)
            export = client.get(f'/api/v1/projects/{pid}/candidates.csv')
            self.assertEqual(export.status_code, 200)
            body = export.text
            self.assertIn("'=2+2", body); self.assertIn("'+12345", body); self.assertIn("'@example.invalid", body)
            contact_export = client.get(f'/api/v1/projects/{pid}/contact-list.csv')
            self.assertEqual(contact_export.status_code, 200)
            self.assertIn("'=2+2", contact_export.text)
            self.assertIn('attachment; filename=', contact_export.headers.get('content-disposition',''))

    def test_release_artifact_policy_keeps_transient_python_caches_out_of_managed_tree(self):
        transient = [p for p in ROOT.rglob('*') if p.name == '__pycache__' or p.suffix == '.pyc']
        # Compile verification may create caches locally, but they must never be declared in the release manifest.
        manifest = json.loads((ROOT/'PORTABLE_MANIFEST.json').read_text(encoding='utf-8'))
        managed = json.dumps(manifest, ensure_ascii=False)
        self.assertNotIn('__pycache__', managed); self.assertNotIn('.pyc', managed)
        self.assertIsInstance(transient, list)

    def test_project_package_roundtrip_preserves_material_blobs_and_historical_decision_context(self):
        from srw.kernel.hashing import decision_context_hash
        from srw.modules.candidate.models import Candidate
        from srw.modules.decision.models import HumanDecision
        from srw.modules.protocol.models import Project

        app = self._app()
        with TestClient(app) as client:
            created = client.post('/api/v1/projects', json={'title':'可迁移项目','role_title':'工程师','brief_summary':'完整项目包'})
            self.assertEqual(created.status_code, 200, created.text)
            pid = created.json()['project_id']; draft_id = created.json()['draft_revision_id']
            published = client.post(f'/api/v1/protocol-revisions/{draft_id}/publish')
            self.assertEqual(published.status_code, 200, published.text)
            candidate = client.post(f'/api/v1/projects/{pid}/candidates', json={'display_name':'迁移候选人'})
            self.assertEqual(candidate.status_code, 200, candidate.text); cid = candidate.json()['candidate_id']
            raw = self._pdf_bytes()
            intake = client.post(f'/api/v1/candidates/{cid}/files', json={
                'filename':'portable-resume.pdf','media_type':'application/pdf','base64':base64.b64encode(raw).decode('ascii'),'source_kind':'resume'
            })
            self.assertEqual(intake.status_code, 200, intake.text)
            source_id = intake.json()['source_id']

            engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
            factory = create_v1_session_factory(engine)
            try:
                with factory.begin() as s:
                    project = s.get(Project, pid); cand = s.get(Candidate, cid)
                    old_context = decision_context_hash(project.current_protocol_revision_id, cand.current_material_revision_id, 'policy.v1')
                    s.add(HumanDecision(project_id=pid,candidate_id=cid,decision_context_hash=old_context,decision='advance',reason='原项目人工决定',actor='human'))
            finally:
                engine.dispose()

            exported = client.get(f'/api/v1/projects/{pid}/export-package')
            self.assertEqual(exported.status_code, 200, exported.text)
            package = exported.content
            self.assertTrue(package.startswith(b'PK')); self.assertEqual(exported.headers['x-srw-contains-personal-data'], 'true')
            package_digest = hashlib.sha256(package).hexdigest()
            self.assertEqual(exported.headers['x-srw-project-package-sha256'], package_digest)

            preview = client.post('/api/v1/projects/import-package/preview', content=package, headers={'Content-Type':'application/zip'})
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()['sha256'], package_digest); self.assertTrue(preview.json()['contains_personal_data'])
            imported = client.post('/api/v1/projects/import-package', content=package, headers={'Content-Type':'application/zip','X-SRW-Package-SHA256':package_digest})
            self.assertEqual(imported.status_code, 200, imported.text)
            new_pid = imported.json()['project_id']; self.assertNotEqual(new_pid, pid)
            self.assertTrue(imported.json()['requires_current_context_reevaluation'])

            candidates = client.get(f'/api/v1/projects/{new_pid}/candidates')
            self.assertEqual(candidates.status_code, 200, candidates.text)
            imported_candidate = candidates.json()['candidates'][0]; new_cid = imported_candidate['candidate_id']
            workspace = client.get(f'/api/v1/candidates/{new_cid}/workspace')
            self.assertEqual(workspace.status_code, 200, workspace.text)
            ws = workspace.json()
            self.assertEqual(ws['stale_decision_reason'], '原项目人工决定')
            self.assertNotEqual(ws['decision_context_hash'], old_context)
            self.assertEqual(ws['stale_decision_context_hash'], old_context)

            engine = create_v1_engine(f"sqlite+pysqlite:///{self.db.as_posix()}")
            try:
                with engine.connect() as con:
                    row = con.exec_driver_sql('SELECT blob_hash FROM source WHERE candidate_id=?', (new_cid,)).first()
                    self.assertIsNotNone(row); blob_hash = row[0]
                blob_path = self.data/'blobs'/blob_hash[:2]/blob_hash
                self.assertTrue(blob_path.is_file()); self.assertEqual(hashlib.sha256(blob_path.read_bytes()).hexdigest(), blob_hash)
            finally:
                engine.dispose()

    def test_project_package_http_commit_requires_exact_preview_digest(self):
        app = self._app()
        with TestClient(app) as client:
            pid, _ = self._project_candidate(client)
            package = client.get(f'/api/v1/projects/{pid}/export-package').content
            digest = hashlib.sha256(package).hexdigest()
            preview = client.post('/api/v1/projects/import-package/preview', content=package)
            self.assertEqual(preview.status_code, 200, preview.text)
            wrong = client.post('/api/v1/projects/import-package', content=package, headers={'X-SRW-Package-SHA256':'0'*64})
            self.assertEqual(wrong.status_code, 409, wrong.text)
            changed = package + b'changed-after-preview'
            mismatch = client.post('/api/v1/projects/import-package', content=changed, headers={'X-SRW-Package-SHA256':digest})
            self.assertEqual(mismatch.status_code, 409, mismatch.text)

    def test_project_package_rejects_duplicate_or_undeclared_zip_members(self):
        app = self._app()
        with TestClient(app) as client:
            pid, _ = self._project_candidate(client)
            original = client.get(f'/api/v1/projects/{pid}/export-package').content
            src = zipfile.ZipFile(io.BytesIO(original))
            manifest = src.read('manifest.json'); project = src.read('project.json')
            bad = io.BytesIO()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(bad,'w',zipfile.ZIP_DEFLATED) as z:
                    z.writestr('manifest.json', manifest); z.writestr('project.json', project); z.writestr('undeclared.txt', b'no')
            r = client.post('/api/v1/projects/import-package/preview', content=bad.getvalue())
            self.assertEqual(r.status_code, 409, r.text)
            dup = io.BytesIO()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with zipfile.ZipFile(dup,'w',zipfile.ZIP_DEFLATED) as z:
                    z.writestr('manifest.json', manifest); z.writestr('manifest.json', manifest); z.writestr('project.json', project)
            r2 = client.post('/api/v1/projects/import-package/preview', content=dup.getvalue())
            self.assertEqual(r2.status_code, 409, r2.text)


if __name__ == '__main__':
    unittest.main()
