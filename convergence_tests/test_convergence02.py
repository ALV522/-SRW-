import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from srw.evidence.grounding import enrich_source_locator
from srw.kernel.hashing import content_hash
from srw.modules.calibration.service import create_anchor, promote_anchor
from srw.modules.candidate.models import Candidate, CandidateContact, Source
from srw.modules.identity.service import scan_project_identity, list_identity_reviews, resolve_identity_review
from srw.modules.protocol.models import Project
from srw.privacy.redaction import redact_personal_data
from srw.privacy.service import build_source_privacy_projection, rebind_privacy_safe_proposals
from srw.providers.contracts import ClaimProposal
from srw.runtime.db.schema import V1_SCHEMA_REVISION, V1SchemaMeta, create_v1_schema
from srw.runtime.db.session import create_v1_engine, create_v1_session_factory


class Convergence02Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "test.db"
        self.engine = create_v1_engine(f"sqlite+pysqlite:///{db}")
        create_v1_schema(self.engine)
        self.factory = create_v1_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _project(self, session, title="Role"):
        row = Project(title=title, status="open")
        session.add(row); session.flush()
        return row

    def test_privacy_projection_preserves_offsets_and_rebinds_safe_quote(self):
        with self.factory() as s:
            p = self._project(s)
            c = Candidate(project_id=p.id, display_name="张三")
            s.add(c); s.flush()
            s.add(CandidateContact(candidate_id=c.id, display_name="张三", phone="13812345678", email="zhangsan@example.com", user_confirmed=True))
            source = Source(candidate_id=c.id, source_kind="resume", content_hash="x"*64, media_type="text/plain", text_content="张三\n电话 13812345678\n邮箱 zhangsan@example.com\n曾负责校园招聘项目，独立招聘20人。", metadata_json="{}")
            s.add(source); s.flush()
            projection = build_source_privacy_projection(s, source)
            self.assertEqual(len(projection.safe_text), len(source.text_content))
            self.assertNotIn("13812345678", projection.safe_text)
            self.assertNotIn("zhangsan@example.com", projection.safe_text)
            quote = "曾负责校园招聘项目，独立招聘20人。"
            proposals = rebind_privacy_safe_proposals(projection, [ClaimProposal("有校园招聘经验", {"quote": quote})])
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0].locator["quote"], quote)
            self.assertTrue(proposals[0].metadata["privacy_scoring_view"])

    def test_privacy_proposal_touching_mask_is_dropped(self):
        text = "姓名：张三 电话：13812345678"
        result = redact_personal_data(text, known_names=["张三"], preserve_length=True)
        self.assertEqual(len(result.text), len(text))
        self.assertGreaterEqual(len(result.spans), 2)

    def test_grounding_enriches_page_and_bbox(self):
        with self.factory() as s:
            p = self._project(s); c = Candidate(project_id=p.id, display_name="A"); s.add(c); s.flush()
            text = "[Page 1]\nPython\n[Page 2]\n招聘分析"
            start = text.index("招聘分析")
            meta = {"extractor": {"grounding_blocks": [{"page": 2, "block_index": 0, "bbox": [10.0,20.0,30.0,40.0], "char_start": start, "char_end": start+4}]}}
            source = Source(candidate_id=c.id, source_kind="resume", content_hash="y"*64, media_type="application/pdf", text_content=text, metadata_json=json.dumps(meta, ensure_ascii=False))
            s.add(source); s.flush()
            locator = enrich_source_locator(source, {"quote": "招聘分析"})
            self.assertEqual(locator["page"], 2)
            self.assertEqual(locator["bbox"], [10.0,20.0,30.0,40.0])
            self.assertEqual(locator["char_start"], start)

    def test_identity_review_queue_does_not_merge(self):
        with self.factory() as s:
            p = self._project(s)
            a = Candidate(project_id=p.id, display_name="A")
            b = Candidate(project_id=p.id, display_name="B")
            s.add_all([a,b]); s.flush()
            s.add_all([
                CandidateContact(candidate_id=a.id, display_name="A", phone="138 1234 5678", email="same@example.com", user_confirmed=True),
                CandidateContact(candidate_id=b.id, display_name="B", phone="+86 13812345678", email="same@example.com", user_confirmed=True),
            ]); s.flush()
            scan = scan_project_identity(s, p.id)
            self.assertEqual(scan["created"], 1)
            reviews = list_identity_reviews(s, p.id, status="pending")
            self.assertEqual(len(reviews), 1)
            self.assertFalse(reviews[0]["merge_performed"])
            resolved = resolve_identity_review(s, reviews[0]["review_id"], status="confirmed_same", actor="reviewer", note="manual check")
            self.assertEqual(resolved["status"], "confirmed_same")
            self.assertIsNotNone(s.get(Candidate, a.id))
            self.assertIsNotNone(s.get(Candidate, b.id))

    def test_anchor_gold_requires_distinct_second_reviewer(self):
        with self.factory() as s:
            p = self._project(s)
            anchor = create_anchor(s, p.id, criterion_key="exp", case_text="case", expected_judgment="met", expected_evidence_level="strong", actor="author")
            aid = anchor["anchor_id"]
            promote_anchor(s, aid, target="human_reviewed", actor="reviewer1")
            promote_anchor(s, aid, target="candidate", actor="reviewer1")
            with self.assertRaises(Exception):
                promote_anchor(s, aid, target="gold", actor="reviewer1")
            gold = promote_anchor(s, aid, target="gold", actor="reviewer2")
            self.assertEqual(gold["lifecycle"], "gold")
            self.assertEqual(gold["second_reviewer"], "reviewer2")


    def test_provider_compatibility_path_receives_redacted_text(self):
        from srw.evidence.pipeline import extract_source_claims
        class FakeRuntime:
            def __init__(self): self.seen = None
            def extract_claims(self, session, *, source_text):
                self.seen = source_text
                return [ClaimProposal("有招聘经验", {"quote": "有三年招聘经验。"})]
        with self.factory() as s:
            p = self._project(s); c = Candidate(project_id=p.id, display_name="张三"); s.add(c); s.flush()
            s.add(CandidateContact(candidate_id=c.id, display_name="张三", phone="13812345678", email="a@example.com", user_confirmed=True))
            source = Source(candidate_id=c.id, source_kind="resume", content_hash="z"*64, media_type="text/plain", text_content="张三 13812345678 a@example.com 有三年招聘经验。", metadata_json="{}")
            s.add(source); s.flush()
            runtime = FakeRuntime()
            result = extract_source_claims(s, source.id, runtime)
            self.assertNotIn("张三", runtime.seen)
            self.assertNotIn("13812345678", runtime.seen)
            self.assertNotIn("a@example.com", runtime.seen)
            self.assertEqual(result.created, 1)

    def test_pdf_importer_emits_grounding_blocks(self):
        import fitz
        from srw.intake.rich_document import OptionalRichDocumentImporter
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Recruiting Experience")
        raw = doc.tobytes(); doc.close()
        imported = OptionalRichDocumentImporter._pdf(raw)
        self.assertIn("Recruiting Experience", imported.text_content)
        blocks = imported.metadata.get("grounding_blocks") or []
        self.assertTrue(blocks)
        self.assertEqual(blocks[0]["page"], 1)
        self.assertLess(blocks[0]["char_start"], blocks[0]["char_end"])

    def test_schema_revision_0009_upgrades_to_0010(self):
        with self.factory() as s:
            meta = s.scalar(select(V1SchemaMeta).limit(1))
            meta.schema_revision = "v1_0009"; s.commit()
        create_v1_schema(self.engine)
        with self.factory() as s:
            meta = s.scalar(select(V1SchemaMeta).limit(1))
            self.assertEqual(meta.schema_revision, V1_SCHEMA_REVISION)


if __name__ == "__main__":
    unittest.main()
