"""S1 UX acceptance: next action, stage stepper, criterion-driven forms.

Real Chromium against a disposable loopback Core. Proves that HR never has to
type a criterion UUID: the published protocol generates the interview outline
and the scorecard rows.
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
KEY = "comm"
TEXT = "Synthetic candidate led a cross-team launch; the launch shipped on time."

PROTOCOL = {
    "brief": {"title": "Backend Engineer", "summary": "Synthetic requisition"},
    "criteria": [{
        "criterion_key": KEY, "name": "沟通能力", "definition": "跨部门沟通",
        "decision_critical": True, "verification_required": False,
        "verification_probes": ["有没有相关经历"], "weight": 1,
    }],
    "assessment_stages": [
        {"stage_key": "resume", "name": "简历筛选", "criteria": [KEY]},
        {"stage_key": "interview", "name": "面试", "criteria": [KEY]},
    ],
    "decision_policy": {"human_final": True},
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CandidateNextActionBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="srw-browser-next-action-",
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
                    raise RuntimeError("Synthetic Core exited")
                try:
                    with urllib.request.urlopen(cls.base + "/health/ready", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Synthetic Core not ready")
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
        time.sleep(0.5)
        cls.temp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(locale="zh-CN")
        self.page = self.context.new_page()
        self.page.set_default_timeout(12000)
        self.page_errors = []
        self.page.on("pageerror", lambda err: self.page_errors.append(str(err)))
        created = self.post("/api/v1/projects", {"title": "Next Action", "role_title": "Engineer"})
        self.pid = created["project_id"]
        self.patch(f"/api/v1/protocol-revisions/{created['draft_revision_id']}", {"payload": PROTOCOL})
        self.post(f"/api/v1/protocol-revisions/{created['draft_revision_id']}/publish", {})
        self.cid = self.post(f"/api/v1/projects/{self.pid}/candidates",
                             {"display_name": "Synthetic Person"})["candidate_id"]
        self.post(f"/api/v1/candidates/{self.cid}/sources/text",
                  {"text_content": TEXT, "publish_material": True})
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        self.page.wait_for_function("Boolean(window.openProject && window.openCandidateNext)")
        self.page.evaluate("pid => window.openProject(pid)", self.pid)
        self.page.evaluate("cid => window.openCandidate(cid)", self.cid)
        expect(self.page.locator(".candidate-steps")).to_be_visible()

    def tearDown(self):
        self.assertFalse(self.page_errors, self.page_errors)
        self.context.close()

    def _request(self, method, path, payload):
        response = self.page.request.fetch(
            self.base + path, method=method, data=json.dumps(payload),
            headers={"content-type": "application/json"})
        self.assertEqual(response.status, 200, response.text())
        return response.json()

    def post(self, path, payload):
        return self._request("POST", path, payload)

    def patch(self, path, payload):
        return self._request("PATCH", path, payload)

    def db(self):
        return sqlite3.connect(Path(self.temp.name) / "data" / "srw_v1.db")

    def test_row_offers_the_next_action_and_the_stepper_opens_the_interview(self):
        self.page.evaluate("window.setProjectTab('candidates')")
        row = self.page.locator("tbody tr").filter(has_text="Synthetic Person")
        expect(row).to_be_visible()
        row_button = row.locator("button.btn.primary")
        expect(row_button).to_have_text("核实事实")
        row_button.click()
        expect(self.page.locator(".candidate-steps")).to_be_visible()
        expect(self.page.locator(".candidate-step")).to_have_count(3)
        expect(self.page.locator(".next-action")).to_contain_text("核实关键事实")
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        expect(self.page.get_by_role("button", name="＋ 面试排期")).to_be_visible()

    def test_interview_form_is_generated_from_the_published_criterion(self):
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        self.page.get_by_role("button", name="＋ 面试排期").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        expect(modal.locator(".criterion-head")).to_contain_text("沟通能力")
        self.assertNotIn("criterion_key", modal.inner_text())
        self.assertNotIn(KEY, modal.inner_text())
        modal.locator(".c-q").fill("请讲一次你推动跨部门协作的经历")
        modal.locator(".c-p").fill("核实跨部门沟通能力")
        self.page.get_by_role("button", name="保存").click()
        expect(self.page.locator(".timeline")).to_contain_text("面试")
        with self.db() as connection:
            questions = json.loads(connection.execute(
                "SELECT metadata_json FROM recruitment_event ORDER BY rowid DESC LIMIT 1").fetchone()[0])["questions"]
        self.assertEqual(questions, [{"criterion_key": KEY,
                                      "question": "请讲一次你推动跨部门协作的经历",
                                      "purpose": "核实跨部门沟通能力", "answer": ""}])

    def test_scorecard_never_asks_for_a_key(self):
        self.post(f"/api/v1/candidates/{self.cid}/events",
                  {"event_type": "interview", "title": "面试", "event_state": "scheduled"})
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.locator("tbody tr").filter(has_text="Synthetic Person").locator("button.btn.primary").click()
        expect(self.page.locator(".candidate-steps")).to_be_visible()
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        self.page.get_by_role("button", name="独立 Scorecard").click()
        modal = self.page.locator(".modal")
        self.assertNotIn("Criterion Key", modal.inner_text())
        self.assertNotIn(KEY, modal.inner_text())
        expect(modal.locator(".criterion-block")).to_have_count(1)
        modal.locator("#sc-evaluator").fill("面试官A")
        modal.locator(".c-obs").fill("主动拉齐三方")
        modal.locator(".c-support").fill("提前完成联调")
        modal.locator(".c-rec").fill("advance")
        modal.locator("#sc-rec").fill("advance")
        self.page.get_by_role("button", name="提交并锁定").click()
        with self.db() as connection:
            feedback = json.loads(connection.execute(
                "SELECT feedback_json FROM interview_scorecard_submission ORDER BY rowid DESC LIMIT 1").fetchone()[0])
        self.assertEqual(feedback[0]["criterion_key"], KEY)
        self.assertEqual(feedback[0]["rating"], "strong")

    def test_completion_form_uses_the_same_criterion_rows(self):
        task = self.post(f"/api/v1/candidates/{self.cid}/events",
                         {"event_type": "interview", "title": "面试", "event_state": "scheduled"})
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.locator("tbody tr").filter(has_text="Synthetic Person").locator("button.btn.primary").click()
        expect(self.page.locator(".candidate-steps")).to_be_visible()
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role("button", name="完成").first.click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        self.assertNotIn(KEY, modal.inner_text())
        modal.locator(".c-obs").fill("如实回答了追问")
        modal.locator(".c-rec").fill("proceed")
        modal.locator("#event-overall").fill("advance")
        self.page.get_by_role("button", name="完成").last.click()
        with self.db() as connection:
            feedback = json.loads(connection.execute(
                "SELECT metadata_json FROM recruitment_event WHERE id=?",
                (task["event_id"],)).fetchone()[0])["feedback"]
        self.assertEqual(feedback[0]["criterion_key"], KEY)


if __name__ == "__main__":
    unittest.main()
