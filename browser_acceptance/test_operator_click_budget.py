"""#206 operator metric: real home -> project -> candidate -> interview feedback.

One disposable Core, SQLite and Chromium; only synthetic data. Counts deliberate
pointer clicks separately from home navigation and from the candidate list;
project/Published criteria/candidates are API-seeded, not counted as HR clicks.
This is Browser acceptance, never Windows WPF acceptance.
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
PROTOCOL = {
    "brief": {"title": "Synthetic Engineer", "summary": "Synthetic requisition"},
    "criteria": [{
        "criterion_key": "synthetic-communication",
        "name": "沟通能力",
        "definition": "与不同团队清晰沟通",
        "verification_probes": ["请描述一次跨团队协作"],
        "decision_critical": True,
        "verification_required": False,
        "weight": 1,
    }],
    "assessment_stages": [
        {"stage_key": "resume", "name": "简历筛选", "criteria": ["synthetic-communication"]},
        {"stage_key": "interview", "name": "面试", "criteria": ["synthetic-communication"]},
    ],
    "decision_policy": {"human_final": True},
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class OperatorClickBudgetAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="srw-operator-budget-",
                                               ignore_cleanup_errors=True)
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = {**os.environ, "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
               "RECRUITMENT_SESSION_ENFORCE": "0", "SRW_BACKGROUND_WORKER": "0"}
        cls.server = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "browser_acceptance" / "serve.py"),
             "--workspace", cls.temp.name, "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if cls.server.poll() is not None:
                    raise RuntimeError("Synthetic Core exited before readiness")
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
        cls.temp.cleanup()

    def test_list_to_completed_interview_and_independent_scorecard(self):
        context = self.browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.set_default_timeout(12000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        clicks = []

        def api(method, path, payload):
            response = page.request.fetch(
                self.base + path, method=method,
                data=json.dumps(payload, ensure_ascii=False),
                headers={"content-type": "application/json"})
            self.assertEqual(response.status, 200, response.text())
            return response.json()

        def click(locator, label, ledger=None):
            locator.click()
            (clicks if ledger is None else ledger).append(label)

        try:
            project = api("POST", "/api/v1/projects",
                          {"title": "Operator Journey", "role_title": "Engineer"})
            pid = project["project_id"]
            draft = project["draft_revision_id"]
            api("PATCH", f"/api/v1/protocol-revisions/{draft}", {"payload": PROTOCOL})
            api("POST", f"/api/v1/protocol-revisions/{draft}/publish", {})
            a = api("POST", f"/api/v1/projects/{pid}/candidates",
                    {"display_name": "Synthetic Candidate A"})["candidate_id"]
            b = api("POST", f"/api/v1/projects/{pid}/candidates",
                    {"display_name": "Synthetic Candidate B"})["candidate_id"]
            api("POST", f"/api/v1/candidates/{b}/sources/text",
                {"text_content": "Synthetic evidence for candidate B",
                 "publish_material": True})
            page.goto(self.base + "/v1", wait_until="domcontentloaded")
            expect(page.locator("#top-title")).to_have_text("今日待办")
            # init() sets the title before its async dashboard render finishes.
            # Wait for content so late dashboard paint cannot detach project rows.
            expect(page.locator(".kpi-card").first).to_be_visible()
            click(page.locator(".nav-item").filter(has_text="招聘项目"),
                  "首页→招聘项目")
            project_row = page.locator("tr").filter(has_text="Operator Journey")
            click(project_row.get_by_role("button", name="进入工作区"),
                  "项目列表→工作区")
            click(page.locator(".tabs").get_by_role("button", name="候选人"),
                  "项目→候选人列表")
            list_start = len(clicks)
            row = page.locator(f'tr[data-candidate-id="{b}"]')
            expect(row).to_be_visible()

            click(row.locator('[data-quick-action="schedule"]'), "列表→安排面试")
            expect(page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Candidate B")
            modal = page.locator(".modal")
            expect(modal.locator(".criterion-block")).to_have_count(1)
            expect(modal).to_contain_text("沟通能力")
            expect(modal).to_contain_text("与不同团队清晰沟通")
            self.assertNotIn("criterion_key", modal.inner_text())
            self.assertNotIn("synthetic-communication", modal.inner_text())
            modal.locator(".c-q").fill("请描述一次跨团队协作")
            click(modal.get_by_role("button", name="保存"), "保存面试排期")
            expect(page.locator("#modal-root .modal")).to_have_count(0)

            timeline = page.locator(".timeline-item").filter(has_text="面试")
            click(timeline.get_by_role("button", name="完成").first, "填写完成反馈")
            completion = page.locator(".modal")
            expect(completion.locator(".criterion-block")).to_have_count(1)
            self.assertNotIn("criterion_key", completion.inner_text())
            completion.locator(".c-obs").fill("候选人B准确说明了跨团队沟通")
            completion.locator(".c-rec").fill("建议进入下一轮")
            click(completion.get_by_role("button", name="完成"), "提交完成反馈")
            expect(page.locator("#modal-root .modal")).to_have_count(0)

            timeline = page.locator(".timeline-item").filter(has_text="面试")
            click(timeline.get_by_role("button", name="独立 Scorecard"), "填写独立面评")
            scorecard = page.locator(".modal")
            self.assertNotIn("criterion_key", scorecard.inner_text())
            scorecard.locator("#sc-evaluator").fill("Synthetic Interviewer")
            scorecard.locator(".c-obs").fill("只属于候选人B的面评")
            scorecard.locator(".c-rec").fill("建议继续")
            scorecard.locator("#sc-rec").fill("advance")
            click(scorecard.get_by_role("button", name="提交并锁定"), "提交并锁定面评")
            expect(page.locator("#modal-root .modal")).to_have_count(0)
            self.assertEqual(list_start, 3, clicks)
            self.assertEqual(len(clicks) - list_start, 6, clicks)
            self.assertEqual(len(clicks), 9, clicks)

            db_path = Path(self.temp.name) / "data" / "srw_v1.db"
            with sqlite3.connect(db_path) as db:
                events = db.execute(
                    "SELECT candidate_id, event_state, metadata_json FROM recruitment_event "
                    "WHERE candidate_id IN (?,?)", (a, b)).fetchall()
                scorecards = db.execute(
                    "SELECT candidate_id, feedback_json FROM interview_scorecard_submission "
                    "WHERE candidate_id IN (?,?)", (a, b)).fetchall()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0][0:2], (b, "completed"))
            self.assertEqual(json.loads(events[0][2])["feedback"][0]["criterion_key"],
                             "synthetic-communication")
            self.assertEqual(len(scorecards), 1)
            self.assertEqual(scorecards[0][0], b)
            self.assertEqual(json.loads(scorecards[0][1])[0]["criterion_key"],
                             "synthetic-communication")

            # The browser's candidate context must not read B's feedback as A.
            # This is a real HTTP read against the same Core/SQLite instance.
            with sqlite3.connect(db_path) as db:
                event_id = db.execute(
                    "SELECT id FROM recruitment_event WHERE candidate_id=?", (b,)
                ).fetchone()[0]
                before_audit = db.execute("SELECT COUNT(*) FROM audit_event").fetchone()[0]
            scoped = (f"/api/v1/projects/{pid}/candidates/{b}"
                      f"/events/{event_id}/scorecards")
            own = page.request.get(self.base + scoped)
            self.assertEqual(own.status, 200, own.text())
            self.assertEqual(own.json()["scorecards"][0]["evaluator"],
                             "Synthetic Interviewer")
            foreign = page.request.get(
                self.base + f"/api/v1/projects/{pid}/candidates/{a}"
                f"/events/{event_id}/scorecards")
            self.assertEqual(foreign.status, 404, foreign.text())
            self.assertNotIn("只属于候选人B的面评", foreign.text())
            self.assertNotIn("Synthetic Interviewer", foreign.text())
            with sqlite3.connect(db_path) as db:
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM audit_event").fetchone()[0],
                    before_audit)
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM interview_scorecard_submission").fetchone()[0],
                    1)

            page.reload(wait_until="domcontentloaded")
            expect(page.locator("#top-title")).to_have_text("今日待办")
            # init() sets the title before its async dashboard render finishes.
            # Wait for content so late dashboard paint cannot detach project rows.
            expect(page.locator(".kpi-card").first).to_be_visible()
            reopen_clicks = []
            click(page.locator(".nav-item").filter(has_text="招聘项目"),
                  "重开→招聘项目", reopen_clicks)
            click(page.locator("tr").filter(has_text="Operator Journey").get_by_role(
                  "button", name="进入工作区"), "重开→项目工作区", reopen_clicks)
            click(page.locator(".tabs").get_by_role("button", name="候选人"),
                  "重开→候选人列表", reopen_clicks)
            row = page.locator(f'tr[data-candidate-id="{b}"]')
            expect(row).to_contain_text("Synthetic Candidate B")
            click(row.get_by_role("button", name="打开工作台"),
                  "重开→候选人B工作台", reopen_clicks)
            expect(page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Candidate B")
            click(page.locator(".candidate-step").filter(has_text="面试"),
                  "重开→面试", reopen_clicks)
            click(page.locator(".timeline-item").filter(has_text="面试").get_by_role(
                  "button", name="独立 Scorecard"), "重开→独立面评", reopen_clicks)
            self.assertEqual(len(reopen_clicks), 6, reopen_clicks)
            expect(page.locator(".modal")).to_contain_text("只属于候选人B的面评")
            self.assertFalse(errors, errors)

            evidence = ROOT / "artifacts" / "browser"
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "operator-click-budget.json").write_text(
                json.dumps({"scenario": "synthetic candidate B home -> feedback",
                            "precondition": "project, Published criteria and candidates API-seeded",
                            "pointer_clicks": len(clicks) - list_start,
                            "pointer_clicks_from_home": len(clicks),
                            "navigation_steps": clicks[:list_start],
                            "steps": clicks[list_start:],
                            "reopen_ui_pointer_clicks": len(reopen_clicks),
                            "reopen_steps": reopen_clicks,
                            "internal_id_input_required": False,
                            "cross_candidate_write": False,
                            "reopen_persisted": True}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            page.screenshot(path=str(evidence / "operator-click-budget.png"), full_page=True)
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()
