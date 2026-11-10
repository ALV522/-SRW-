"""#198: real Chromium manual Source selection → Claim → separate human review.

Disposable loopback Core, synthetic text/SQLite, no Provider or production files.
This does not claim Windows WPF/Native acceptance.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TEXT = "Synthetic 😀 candidate shipped a service; candidate shipped a service."


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ManualClaimBrowserAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="srw-browser-manual-",
                                               ignore_cleanup_errors=True)
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = {**os.environ, "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
               "RECRUITMENT_SESSION_ENFORCE": "0", "SRW_BACKGROUND_WORKER": "0"}
        cls.server = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "browser_acceptance" / "serve.py"),
             "--workspace", cls.temp.name, "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            for _ in range(100):
                if cls.server.poll() is not None:
                    raise RuntimeError("Synthetic manual-claim Core exited")
                try:
                    with urllib.request.urlopen(cls.base + "/health/ready", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Synthetic manual-claim Core not ready")
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except BaseException:
            cls.server.terminate()
            cls.server.wait(timeout=10)
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=10)
        cls.temp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(locale="zh-CN")
        self.page = self.context.new_page()
        self.page.set_default_timeout(12000)
        self.page_errors = []
        self.page.on("pageerror", lambda err: self.page_errors.append(str(err)))
        self.pid = self.post("/api/v1/projects", {"title": "Manual E2E", "role_title": "Engineer"})["project_id"]
        self.cid = self.post(f"/api/v1/projects/{self.pid}/candidates",
                             {"display_name": "Synthetic Person"})["candidate_id"]
        self.sid = self.post(f"/api/v1/candidates/{self.cid}/sources/text",
                             {"text_content": TEXT, "publish_material": True})["source_id"]
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        self.page.wait_for_function("Boolean(window.openProject && window.openCandidate && window.srwManualClaimOpen && typeof window.srwApi === 'function')")
        self.page.wait_for_function("document.querySelector('#top-title')?.textContent === '今日待办'")
        self.page.evaluate("""async ([pid,cid]) => {
            await window.openProject(pid);
            await window.openCandidate(cid);
        }""", [self.pid, self.cid])

    def tearDown(self):
        self.assertFalse(self.page_errors, self.page_errors)
        self.context.close()

    def post(self, path, payload):
        response = self.page.request.post(self.base + path, data=payload)
        self.assertEqual(response.status, 200, response.text())
        return response.json()

    def count(self, table):
        db = Path(self.temp.name) / "data" / "srw_v1.db"
        with sqlite3.connect(db) as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def candidate_claim_count(self):
        db = Path(self.temp.name) / "data" / "srw_v1.db"
        with sqlite3.connect(db) as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM claim WHERE candidate_id=?", (self.cid,)
            ).fetchone()[0]

    def manual_claim_audit_count(self):
        db = Path(self.temp.name) / "data" / "srw_v1.db"
        with sqlite3.connect(db) as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM audit_event WHERE event_type='CLAIM_PROPOSED_MANUALLY'"
            ).fetchone()[0]

    def select_quote(self, quote):
        self.page.locator("#srw-manual-source").evaluate("""(element, quote) => {
            const start = element.value.lastIndexOf(quote);
            if (start < 0) throw new Error("synthetic quote missing");
            element.focus();
            element.setSelectionRange(start, start + quote.length);
        }""", quote)
        self.page.get_by_role("button", name="引用选中文本").click()

    def test_unicode_offset_and_separate_human_review(self):
        before_audit = self.manual_claim_audit_count()
        self.page.get_by_role("button", name="人工提出 Claim").click()
        expect(self.page.locator("#srw-manual-submit")).to_be_disabled()
        self.select_quote("candidate shipped a service")
        expect(self.page.locator("#srw-manual-submit")).to_be_enabled()
        self.page.locator("#srw-manual-normalized").fill("Shipped a service")
        self.page.get_by_role("button", name="提交待核实 Claim").click()
        expect(self.page.locator(".claim.unreviewed")).to_have_count(1)
        self.assertEqual(self.candidate_claim_count(), 1)
        with sqlite3.connect(Path(self.temp.name) / "data" / "srw_v1.db") as connection:
            row = connection.execute("SELECT id, source_locator_json FROM claim ORDER BY rowid DESC LIMIT 1").fetchone()
            audit_count = connection.execute(
                "SELECT COUNT(*) FROM audit_event WHERE event_type='CLAIM_PROPOSED_MANUALLY'"
            ).fetchone()[0]
        self.assertEqual(json.loads(row[1])["char_start"], TEXT.rindex("candidate shipped"))
        self.assertEqual(audit_count, before_audit + 1)
        self.page.locator(".claim.unreviewed").get_by_role("button", name="确认事实").click()
        expect(self.page.locator(".claim.confirmed")).to_have_count(1)
        self.assertEqual(self.candidate_claim_count(), 1)

    def test_material_revision_invalidated_before_submit_fails_closed(self):
        before_audit = self.manual_claim_audit_count()
        self.page.get_by_role("button", name="人工提出 Claim").click()
        self.select_quote("candidate shipped a service")
        self.page.locator("#srw-manual-normalized").fill("Shipped a service")
        # Simulate a material revision becoming unavailable after the modal
        # was opened. No client-side cache may authorize a new Claim.
        with sqlite3.connect(Path(self.temp.name) / "data" / "srw_v1.db") as connection:
            connection.execute(
                "UPDATE candidate SET current_material_revision_id=NULL WHERE id=?",
                (self.cid,),
            )
            connection.commit()
        self.page.get_by_role("button", name="提交待核实 Claim").click()
        expect(self.page.get_by_text("提交未完成", exact=False)).to_be_visible()
        self.assertEqual(self.candidate_claim_count(), 0)
        self.assertEqual(self.manual_claim_audit_count(), before_audit)

    def test_manual_claim_survives_reload_and_never_moves_to_another_candidate(self):
        # Other tests share this disposable SQLite; count only this test's delta.
        before_claims = self.count("claim")
        with sqlite3.connect(Path(self.temp.name) / "data" / "srw_v1.db") as db:
            before_audit = db.execute(
                "SELECT COUNT(*) FROM audit_event WHERE event_type='CLAIM_PROPOSED_MANUALLY'"
            ).fetchone()[0]
        # This is an operator workflow with no Provider request or background worker.
        self.page.get_by_role("button", name="人工提出 Claim").click()
        self.select_quote("candidate shipped a service")
        self.page.locator("#srw-manual-normalized").fill("Persistent manual evidence")
        self.page.get_by_role("button", name="提交待核实 Claim").click()
        expect(self.page.locator(".claim.unreviewed")).to_have_count(1)

        other = self.post(f"/api/v1/projects/{self.pid}/candidates",
                          {"display_name": "Synthetic Other Person"})["candidate_id"]
        self.page.evaluate("""async ([pid, cid]) => {
            await window.openProject(pid);
            await window.openCandidate(cid);
        }""", [self.pid, other])
        expect(self.page.locator(".claim.unreviewed")).to_have_count(0)

        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_function("Boolean(window.openProject && window.openCandidate && typeof window.srwApi === 'function')")
        self.page.evaluate("""async ([pid, cid]) => {
            await window.openProject(pid);
            await window.openCandidate(cid);
        }""", [self.pid, self.cid])
        expect(self.page.locator(".claim.unreviewed")).to_have_count(1)
        with sqlite3.connect(Path(self.temp.name) / "data" / "srw_v1.db") as db:
            rows = db.execute(
                "SELECT candidate_id FROM claim WHERE candidate_id=?", (self.cid,)
            ).fetchall()
            audit = db.execute(
                "SELECT COUNT(*) FROM audit_event WHERE event_type='CLAIM_PROPOSED_MANUALLY'"
            ).fetchone()[0]
        self.assertEqual(rows, [(self.cid,)])
        self.assertEqual(audit, before_audit + 1)
        self.page.locator(".claim.unreviewed").get_by_role(
            "button", name="确认事实").click()
        expect(self.page.locator(".claim.confirmed")).to_have_count(1)

        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_function("Boolean(window.openProject && window.openCandidate && typeof window.srwApi === 'function')")
        self.page.evaluate("""async ([pid, cid]) => {
            await window.openProject(pid);
            await window.openCandidate(cid);
        }""", [self.pid, self.cid])
        expect(self.page.locator(".claim.confirmed")).to_have_count(1)
        self.assertEqual(self.count("claim"), before_claims + 1)

    def test_no_quote_selection_cannot_write(self):
        before_audit = self.manual_claim_audit_count()
        self.page.get_by_role("button", name="人工提出 Claim").click()
        self.page.get_by_role("button", name="引用选中文本").click()
        expect(self.page.locator("#srw-manual-submit")).to_be_disabled()
        self.assertEqual(self.candidate_claim_count(), 0)
        self.assertEqual(self.manual_claim_audit_count(), before_audit)


if __name__ == "__main__":
    unittest.main()
