"""S1a acceptance: protocol-pinned interview forms, scorecards and completion.

Real Chromium against a disposable loopback Core plus real SQLite assertions.
The contract under test (PR #207 review): only the *Published* protocol may
generate structured interview content, every event/scorecard stays bound to the
candidate and protocol revision it was created under, and a revision change
fails closed instead of silently remapping criterion keys.
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
from contextlib import closing
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
KEY = "comm"
KEY_R2 = "delivery"
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

PROTOCOL_SAME_KEY_R2 = {
    "brief": {"title": "Backend Engineer", "summary": "Same key, new definition"},
    "criteria": [{
        "criterion_key": KEY, "name": "沟通能力", "definition": "跨部门影响力与向上沟通",
        "decision_critical": True, "verification_required": False,
        "verification_probes": ["讲一次你说服上级调整排期的经历"], "weight": 1,
    }],
    "assessment_stages": [
        {"stage_key": "resume", "name": "简历筛选", "criteria": [KEY]},
        {"stage_key": "interview", "name": "面试", "criteria": [KEY]},
    ],
    "decision_policy": {"human_final": True},
}

PROTOCOL_XSS = {
    "brief": {"title": "Escape Check", "summary": "Synthetic"},
    "criteria": [{
        "criterion_key": KEY,
        "name": '沟通<img src=x onerror="window.__xss=1">',
        "definition": "跨部门 <script>window.__xss2=1</script> 协作",
        "decision_critical": True, "verification_required": False,
        "verification_probes": ['请讲<img src=x onerror="window.__xss3=1">一次'],
        "weight": 1,
    }],
    "assessment_stages": [
        {"stage_key": "interview", "name": "面试", "criteria": [KEY]},
    ],
    "decision_policy": {"human_final": True},
}

PROTOCOL_R2 = {
    "brief": {"title": "Backend Engineer", "summary": "Synthetic requisition v2"},
    "criteria": [{
        "criterion_key": KEY_R2, "name": "交付能力", "definition": "按期交付",
        "decision_critical": True, "verification_required": False,
        "verification_probes": ["讲一次按期交付的项目"], "weight": 1,
    }],
    "assessment_stages": [
        {"stage_key": "resume", "name": "简历筛选", "criteria": [KEY_R2]},
        {"stage_key": "interview", "name": "面试", "criteria": [KEY_R2]},
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

    # ------------------------------------------------------------------ helpers
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

    def get(self, path):
        response = self.page.request.get(self.base + path)
        self.assertEqual(response.status, 200, response.text())
        return response.json()

    def db(self):
        return sqlite3.connect(Path(self.temp.name) / "data" / "srw_v1.db")

    def counts(self, cid):
        with closing(self.db()) as connection:
            return {
                "events": connection.execute(
                    "SELECT COUNT(*) FROM recruitment_event WHERE candidate_id=?", (cid,)).fetchone()[0],
                "scorecards": connection.execute(
                    "SELECT COUNT(*) FROM interview_scorecard_submission WHERE candidate_id=?",
                    (cid,)).fetchone()[0],
                "sources": connection.execute(
                    "SELECT COUNT(*) FROM source WHERE candidate_id=?", (cid,)).fetchone()[0],
                "audits": connection.execute(
                    "SELECT COUNT(*) FROM audit_event WHERE candidate_id=?", (cid,)).fetchone()[0],
            }

    def publish_next(self, pid, payload):
        forked = self.post(f"/api/v1/projects/{pid}/protocol-drafts", {})
        revision = forked["revision_id"]
        self.patch(f"/api/v1/protocol-revisions/{revision}", {"payload": payload})
        self.post(f"/api/v1/protocol-revisions/{revision}/publish", {})
        return revision

    def open_step(self, cid, step="面试"):
        self.page.evaluate("cid => window.openCandidate(cid)", cid)
        expect(self.page.locator(".candidate-steps")).to_be_visible()
        self.page.locator(".candidate-step").filter(has_text=step).click()

    def schedule_interview(self, cid=None, question="请说明一次跨部门协作经历"):
        cid = cid or self.cid
        self.open_step(cid)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        modal.locator(".c-q").fill(question)
        self.page.get_by_role("button", name="保存").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with closing(self.db()) as connection:
            row = connection.execute(
                "SELECT id, metadata_json FROM recruitment_event "
                "WHERE candidate_id=? ORDER BY rowid DESC LIMIT 1", (cid,)).fetchone()
        return row[0], json.loads(row[1])

    def test_delayed_assessment_cannot_repaint_another_candidate(self):
        """A late Core assessment response cannot restore the previous HR workspace."""
        other = self.post(f"/api/v1/projects/{self.pid}/candidates",
                          {"display_name": "Synthetic Other"})["candidate_id"]
        self.post(f"/api/v1/candidates/{other}/sources/text",
                  {"text_content": TEXT, "publish_material": True})
        workspace = self.get(f"/api/v1/candidates/{self.cid}/workspace")
        self.assertTrue(workspace.get("decision_context_hash"),
                        "synthetic Published/material fixture must exercise assessment GET")
        # Delay only one real HTTP response. Every other Core/SQLite read stays real.
        self.page.evaluate("""cid => {
          const originalFetch = window.fetch.bind(window);
          window.__assessmentHeld = false;
          window.__releaseAssessment = null;
          window.fetch = async (...args) => {
            if (String(args[0]).includes('/api/v1/candidates/' + cid + '/assessment')) {
              window.__assessmentHeld = true;
              await new Promise(resolve => { window.__releaseAssessment = resolve; });
            }
            return originalFetch(...args);
          };
        }""", self.cid)
        self.page.evaluate("cid => { void window.openCandidate(cid); }", self.cid)
        self.page.wait_for_function("window.__assessmentHeld === true")
        self.page.evaluate("cid => { void window.openCandidate(cid); }", other)
        expect(self.page.locator("#content h1")).to_have_text("Synthetic Other")
        self.page.evaluate("window.__releaseAssessment()")
        self.page.wait_for_timeout(300)
        expect(self.page.locator("#content h1")).to_have_text("Synthetic Other")
        expect(self.page.locator("#top-crumb")).to_contain_text("Synthetic Other")


    def test_late_scorecard_read_cannot_overlay_another_candidate(self):
        """A delayed real Scorecard GET cannot reopen A's modal over candidate B."""
        event_id, _ = self.schedule_interview()
        other = self.post(f"/api/v1/projects/{self.pid}/candidates",
                          {"display_name": "Synthetic Other"})["candidate_id"]
        self.post(f"/api/v1/candidates/{other}/sources/text",
                  {"text_content": TEXT, "publish_material": True})
        before_a, before_b = self.counts(self.cid), self.counts(other)
        self.page.evaluate("""args => {
          const originalFetch = window.fetch.bind(window);
          window.__originalScorecardFetch = originalFetch;
          window.__scorecardHeld = false;
          window.__releaseScorecard = null;
          window.fetch = async (...requestArgs) => {
            const url = String(requestArgs[0]);
            const expected = '/api/v1/projects/' + args.pid + '/candidates/' +
                             args.cid + '/events/' + args.eid + '/scorecards';
            if (url.includes(expected) &&
                (!requestArgs[1]?.method || requestArgs[1].method === 'GET')) {
              window.__scorecardHeld = true;
              await new Promise(resolve => { window.__releaseScorecard = resolve; });
            }
            return originalFetch(...requestArgs);
          };
        }""", {"pid": self.pid, "cid": self.cid, "eid": event_id})
        self.page.evaluate("""args => {
          window.__scorecardDone = false;
          void window.openScorecards(args.cid, args.eid)
            .finally(() => { window.__scorecardDone = true; });
        }""", {"cid": self.cid, "eid": event_id})
        self.page.wait_for_function("window.__scorecardHeld === true")
        self.page.evaluate("cid => window.openCandidate(cid)", other)
        expect(self.page.locator("#content h1")).to_have_text("Synthetic Other")
        self.page.evaluate("window.__releaseScorecard()")
        self.page.wait_for_function("window.__scorecardDone === true")
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        expect(self.page.locator("#top-crumb")).to_contain_text("Synthetic Other")
        self.assertEqual(self.counts(self.cid), before_a)
        self.assertEqual(self.counts(other), before_b)

        # Even an already-open A form cannot submit after the workspace moves.
        self.page.evaluate("window.fetch = window.__originalScorecardFetch")
        self.page.evaluate("cid => window.openCandidate(cid)", self.cid)
        self.page.evaluate("args => window.openScorecards(args.cid,args.eid)",
                           {"cid": self.cid, "eid": event_id})
        modal = self.page.locator("#modal-root .modal")
        expect(modal).to_be_visible()
        modal.locator("#sc-evaluator").fill("Synthetic Reviewer")
        modal.locator(".c-obs").fill("Observation for A only")
        self.page.evaluate("cid => window.openCandidate(cid)", other)
        self.page.evaluate("args => window.saveScorecard(args.cid,args.eid)",
                           {"cid": self.cid, "eid": event_id})
        expect(self.page.locator("#toast-root")).to_contain_text("已阻止提交")
        self.assertEqual(self.counts(self.cid), before_a)
        self.assertEqual(self.counts(other), before_b)

    def test_pending_scorecard_read_cannot_replace_newer_interview_dialog(self):
        """A delayed Scorecard GET must not overwrite a newer HR dialog in the same workspace."""
        event_id, _ = self.schedule_interview()
        before = self.counts(self.cid)
        self.page.evaluate("""args => {
          const originalFetch = window.fetch.bind(window);
          window.__originalScorecardFetch = originalFetch;
          window.__scorecardHeld = false;
          window.fetch = async (...requestArgs) => {
            const url = String(requestArgs[0]);
            const expected = '/api/v1/projects/' + args.pid + '/candidates/' +
                             args.cid + '/events/' + args.eid + '/scorecards';
            if (url.includes(expected) &&
                (!requestArgs[1]?.method || requestArgs[1].method === 'GET')) {
              window.__scorecardHeld = true;
              await new Promise(resolve => { window.__releaseScorecard = resolve; });
            }
            return originalFetch(...requestArgs);
          };
        }""", {"pid": self.pid, "cid": self.cid, "eid": event_id})
        self.page.evaluate("""args => {
          window.__scorecardDone = false;
          void window.openScorecards(args.cid, args.eid)
            .finally(() => { window.__scorecardDone = true; });
        }""", {"cid": self.cid, "eid": event_id})
        self.page.wait_for_function("window.__scorecardHeld === true")
        # A new interview dialog is an explicit later operator action.
        self.page.evaluate("cid => window.openEvent(cid, 'interview')", self.cid)
        expect(self.page.locator("#modal-root .modal h3")).to_have_text("新增结构化面试")
        self.page.evaluate("window.__releaseScorecard()")
        self.page.wait_for_function("window.__scorecardDone === true")
        expect(self.page.locator("#modal-root .modal h3")).to_have_text("新增结构化面试")
        self.page.evaluate("window.closeModal()")
        self.assertEqual(self.counts(self.cid), before)

    def test_pending_scorecard_post_does_not_close_newer_interview_dialog(self):
        """A successful older Scorecard POST must not discard a newer unsaved HR form."""
        event_id, _ = self.schedule_interview()
        before = self.counts(self.cid)
        self.page.evaluate("args => window.openScorecards(args.cid,args.eid)",
                           {"cid": self.cid, "eid": event_id})
        modal = self.page.locator("#modal-root .modal")
        expect(modal.locator("h3")).to_have_text("独立 Interview Scorecard")
        modal.locator("#sc-evaluator").fill("Synthetic Reviewer")
        modal.locator(".c-obs").fill("Observed interview only")

        # Hold the real HTTP POST before sending it; release it after the HR
        # opens and edits another modal in the same candidate workspace.
        self.page.evaluate("""eid => {
          const originalFetch = window.fetch.bind(window);
          window.__scorecardPostHeld = false;
          window.__releaseScorecardPost = null;
          window.fetch = async (...args) => {
            const url = String(args[0]);
            if (url.includes('/api/v1/events/' + eid + '/scorecards') &&
                String(args[1]?.method || 'GET').toUpperCase() === 'POST') {
              window.__scorecardPostHeld = true;
              await new Promise(resolve => { window.__releaseScorecardPost = resolve; });
            }
            return originalFetch(...args);
          };
        }""", event_id)
        self.page.evaluate("""args => {
          window.__scorecardSubmitDone = false;
          void window.saveScorecard(args.cid,args.eid)
            .finally(() => { window.__scorecardSubmitDone = true; });
        }""", {"cid": self.cid, "eid": event_id})
        self.page.wait_for_function("window.__scorecardPostHeld === true")
        self.page.evaluate("cid => window.openEvent(cid, 'interview')", self.cid)
        newer = self.page.locator("#modal-root .modal")
        expect(newer.locator("h3")).to_have_text("新增结构化面试")
        newer.locator(".c-q").fill("UNSAVED synthetic follow-up question")

        self.page.evaluate("window.__releaseScorecardPost()")
        self.page.wait_for_function("window.__scorecardSubmitDone === true")
        expect(newer.locator("h3")).to_have_text("新增结构化面试")
        expect(newer.locator(".c-q")).to_have_value("UNSAVED synthetic follow-up question")
        after = self.counts(self.cid)
        self.assertEqual(after["scorecards"], before["scorecards"] + 1)
        self.assertEqual(after["events"], before["events"])
        with closing(self.db()) as connection:
            row = connection.execute(
                "SELECT event_id FROM interview_scorecard_submission "
                "WHERE candidate_id=? ORDER BY rowid DESC LIMIT 1",
                (self.cid,)).fetchone()
        self.assertEqual(row[0], event_id)
        self.page.evaluate("window.closeModal()")

    # ------------------------------------------------------------------- S1a UI
    def test_row_opens_the_workspace_and_the_stepper_shows_the_next_action(self):
        self.page.evaluate("window.setProjectTab('candidates')")
        row = self.page.locator("tbody tr").filter(has_text="Synthetic Person")
        expect(row).to_be_visible()
        row_button = row.locator("button.btn.primary")
        # A row never asserts "verified"/"should offer"; it only navigates.
        expect(row_button).to_have_text("打开工作台")
        row_button.click()
        expect(self.page.locator(".candidate-steps")).to_be_visible()
        expect(self.page.locator(".candidate-step")).to_have_count(3)
        expect(self.page.locator(".next-action")).to_contain_text("核实关键事实")
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        expect(self.page.get_by_role("button", name="＋ 面试排期")).to_be_visible()

    def test_interview_form_is_generated_from_the_published_criterion(self):
        event_id, metadata = self.schedule_interview()
        with closing(self.db()) as connection:
            stored = json.loads(connection.execute(
                "SELECT metadata_json FROM recruitment_event WHERE id=?", (event_id,)).fetchone()[0])
        self.assertEqual(stored["questions"], [{"criterion_key": KEY,
                                                "question": "请说明一次跨部门协作经历",
                                                "purpose": "", "answer": ""}])
        self.assertEqual(stored["criteria_snapshot"],
                         [{"criterion_key": KEY, "name": "沟通能力", "definition": "跨部门沟通"}])
        published = self.get(f"/api/v1/projects/{self.pid}/protocol-workspace")
        self.assertEqual(stored["protocol_revision_id"], published["current_revision_id"])
        self.assertEqual(metadata["criteria_snapshot"][0]["name"], "沟通能力")

    def test_scorecard_never_asks_for_a_key(self):
        event_id, _ = self.schedule_interview()
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="独立 Scorecard").click()
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
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with closing(self.db()) as connection:
            row = connection.execute(
                "SELECT event_id, feedback_json FROM interview_scorecard_submission "
                "ORDER BY rowid DESC LIMIT 1").fetchone()
        self.assertEqual(row[0], event_id)
        feedback = json.loads(row[1])
        self.assertEqual(feedback[0]["criterion_key"], KEY)
        self.assertEqual(feedback[0]["rating"], "strong")

    def test_completion_form_uses_the_event_criterion_rows_and_keeps_questions(self):
        event_id, metadata = self.schedule_interview()
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="完成").first.click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        self.assertNotIn(KEY, modal.inner_text())
        modal.locator(".c-obs").fill("如实回答了追问")
        modal.locator(".c-rec").fill("proceed")
        modal.locator("#event-overall").fill("advance")
        self.page.get_by_role("button", name="完成").last.click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with closing(self.db()) as connection:
            stored = json.loads(connection.execute(
                "SELECT metadata_json FROM recruitment_event WHERE id=?", (event_id,)).fetchone()[0])
        self.assertEqual(stored["questions"], metadata["questions"])
        self.assertEqual(stored["protocol_revision_id"], metadata["protocol_revision_id"])
        self.assertEqual(stored["feedback"][0]["criterion_key"], KEY)

    def test_phone_screen_completion_keeps_notes_only(self):
        """A phone screen has no interview-stage criteria and must stay usable.

        Refusing structured feedback must not remove the plain note path.
        """
        self.open_step(self.cid)
        self.page.get_by_role("button", name="＋ 电话筛选").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".notice.danger")).to_have_count(0)
        expect(modal.locator(".criterion-block")).to_have_count(0)
        self.page.get_by_role("button", name="保存").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with closing(self.db()) as connection:
            event_id, state, raw = connection.execute(
                "SELECT id, event_state, metadata_json FROM recruitment_event "
                "WHERE candidate_id=? ORDER BY rowid DESC LIMIT 1", (self.cid,)).fetchone()
        self.assertEqual(state, "scheduled")
        self.assertEqual(json.loads(raw)["questions"], [])
        before = self.counts(self.cid)

        self.page.locator(".timeline-item").filter(has_text="电话筛选").get_by_role(
            "button", name="完成").first.click()
        plain = self.page.locator(".modal")
        expect(plain.locator("#event-notes")).to_be_visible()
        expect(plain.locator(".criterion-block")).to_have_count(0)
        plain.locator("#event-outcome").select_option("proceed")
        plain.locator("#event-notes").fill("电话沟通顺畅，约定下周面试")
        self.page.get_by_role("button", name="完成").last.click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)

        with closing(self.db()) as connection:
            state2, notes = connection.execute(
                "SELECT event_state, notes FROM recruitment_event WHERE id=?", (event_id,)).fetchone()
        self.assertEqual(state2, "completed")
        self.assertEqual(notes, "电话沟通顺畅，约定下周面试")
        after = self.counts(self.cid)
        self.assertEqual(after["scorecards"], before["scorecards"])
        self.assertEqual(after["sources"], before["sources"])

    # ------------------------------------------- same key, new revision (R1 -> R2)
    def test_same_key_new_revision_blocks_history(self):
        """A newer revision with the *same* key but a new definition still blocks."""
        event_id, metadata = self.schedule_interview()
        before = self.counts(self.cid)
        self.publish_next(self.pid, PROTOCOL_SAME_KEY_R2)

        self.open_step(self.cid)
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="完成").first.click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".notice.danger")).to_be_visible()
        expect(modal.locator(".notice.danger")).to_contain_text("旧的标准版本")
        self.assertEqual(modal.get_by_role("button", name="完成").count(), 0)
        self.page.get_by_role("button", name="关闭").click()

        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="独立 Scorecard").click()
        scorecard_modal = self.page.locator(".modal")
        # History stays readable; the new write is what gets refused.
        expect(scorecard_modal.locator(".notice")).to_be_visible()
        expect(scorecard_modal.locator(".notice")).to_contain_text("只读")
        expect(scorecard_modal.locator(".notice")).to_contain_text("旧的标准版本")
        self.assertEqual(scorecard_modal.get_by_role("button", name="提交并锁定").count(), 0)
        self.page.get_by_role("button", name="关闭").click()

        self.assertEqual(self.counts(self.cid), before)
        with closing(self.db()) as connection:
            stored = json.loads(connection.execute(
                "SELECT metadata_json FROM recruitment_event WHERE id=?", (event_id,)).fetchone()[0])
        self.assertEqual(stored, metadata)

    # ------------------------------- history stays readable after a revision swap
    def test_historical_scorecard_stays_readable_after_revision_change(self):
        event_id, _ = self.schedule_interview()
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="独立 Scorecard").click()
        modal = self.page.locator(".modal")
        modal.locator("#sc-evaluator").fill("历史面试官")
        modal.locator(".c-rating").select_option("strong")
        modal.locator(".c-obs").fill("R1 版本下的真实面评")
        modal.locator(".c-support").fill("上线提前两周完成")
        modal.locator(".c-counter").fill("跨部门依赖仍有风险")
        modal.locator(".c-rec").fill("建议先核实跨部门依赖")
        self.page.get_by_role("button", name="提交并锁定").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        before = self.counts(self.cid)
        with closing(self.db()) as connection:
            stored_before = connection.execute(
                "SELECT feedback_json FROM interview_scorecard_submission WHERE event_id=?",
                (event_id,)).fetchone()[0]

        self.publish_next(self.pid, PROTOCOL_R2)
        self.open_step(self.cid)
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="独立 Scorecard").click()
        readonly = self.page.locator(".modal")
        # The submitted per-criterion evidence must actually be visible.
        expect(readonly).to_contain_text("历史面试官")
        expect(readonly).to_contain_text("沟通能力")
        expect(readonly).not_to_contain_text("交付能力")
        expect(readonly).to_contain_text("强")
        expect(readonly).to_contain_text("R1 版本下的真实面评")
        expect(readonly).to_contain_text("上线提前两周完成")
        expect(readonly).to_contain_text("跨部门依赖仍有风险")
        expect(readonly.locator(".scorecard-history thead")).to_contain_text("逐项建议")
        expect(readonly.locator(".scorecard-history tbody tr")).to_contain_text("建议先核实跨部门依赖")
        self.assertNotIn(KEY, readonly.inner_text())
        expect(readonly.locator(".notice")).to_contain_text("只读")
        self.assertEqual(readonly.get_by_role("button", name="提交并锁定").count(), 0)
        self.assertEqual(readonly.locator("#sc-evaluator").count(), 0)
        self.page.get_by_role("button", name="关闭").click()

        self.assertEqual(self.counts(self.cid), before)
        with closing(self.db()) as connection:
            stored_after = connection.execute(
                "SELECT feedback_json FROM interview_scorecard_submission WHERE event_id=?",
                (event_id,)).fetchone()[0]
        self.assertEqual(stored_after, stored_before)

    # ----------------------------- legacy history without a pinned revision is readable
    def test_legacy_scorecard_without_pinned_revision_is_read_only(self):
        created = self.post(f"/api/v1/candidates/{self.cid}/events",
                            {"event_type": "interview", "title": "旧面试", "event_state": "completed",
                             "metadata": {"questions": [{"criterion_key": KEY, "question": "旧问题"}]}})
        event_id = created["event_id"]
        self.post(f"/api/v1/events/{event_id}/scorecards",
                  {"evaluator": "旧评价者", "recommendation": "hold", "submit": True,
                   "feedback": [{"criterion_key": KEY, "rating": "concern",
                                 "observation": "旧版本记录",
                                  "recommendation": "<img src=x onerror=alert(1)>"}]})
        before = self.counts(self.cid)

        self.open_step(self.cid)
        self.page.locator(".timeline-item").filter(has_text="旧面试").get_by_role(
            "button", name="独立 Scorecard").click()
        readonly = self.page.locator(".modal")
        expect(readonly).to_contain_text("旧评价者")
        # No snapshot on a legacy event: neutral label, never the raw key.
        expect(readonly).to_contain_text("历史标准 1")
        expect(readonly).to_contain_text("旧版本记录")
        expect(readonly.locator(".scorecard-history thead")).to_contain_text("逐项建议")
        expect(readonly).to_contain_text("<img src=x onerror=alert(1)>")
        self.assertEqual(readonly.locator(".scorecard-history img").count(), 0)
        self.assertNotIn(KEY, readonly.inner_text())
        expect(readonly.locator(".notice")).to_contain_text("没有保存创建时的标准版本")
        self.assertEqual(readonly.get_by_role("button", name="提交并锁定").count(), 0)
        self.page.get_by_role("button", name="关闭").click()
        self.assertEqual(self.counts(self.cid), before)

    # ------------------------------------- legacy structured event, no pinned rev
    def test_legacy_event_without_pinned_revision_is_read_only(self):
        self.post(f"/api/v1/candidates/{self.cid}/events",
                  {"event_type": "interview", "title": "旧面试", "event_state": "completed",
                   "metadata": {"questions": [{"criterion_key": KEY, "question": "旧问题"}]}})
        self.open_step(self.cid)
        self.page.locator(".timeline-item").filter(has_text="旧面试").get_by_role(
            "button", name="独立 Scorecard").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".notice")).to_be_visible()
        expect(modal.locator(".notice")).to_contain_text("没有保存创建时的标准版本")
        self.assertEqual(modal.get_by_role("button", name="提交并锁定").count(), 0)
        self.page.get_by_role("button", name="关闭").click()
        self.assertEqual(self.counts(self.cid)["scorecards"], 0)

    # ------------------------------------------- criterion text is escaped, key hidden
    def test_criterion_text_is_escaped_and_the_key_stays_hidden(self):
        created = self.post("/api/v1/projects", {"title": "Escape", "role_title": "Engineer"})
        pid = created["project_id"]
        self.patch(f"/api/v1/protocol-revisions/{created['draft_revision_id']}",
                   {"payload": PROTOCOL_XSS})
        self.post(f"/api/v1/protocol-revisions/{created['draft_revision_id']}/publish", {})
        cid = self.post(f"/api/v1/projects/{pid}/candidates",
                        {"display_name": "Escape Person"})["candidate_id"]
        self.page.evaluate("pid => window.openProject(pid)", pid)
        self.open_step(cid)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        self.assertEqual(modal.locator("img").count(), 0)
        self.assertEqual(modal.locator("script").count(), 0)
        self.assertIsNone(self.page.evaluate("window.__xss"))
        self.assertIsNone(self.page.evaluate("window.__xss2"))
        text = modal.inner_text()
        self.assertIn('<img src=x onerror="window.__xss=1">', text)
        self.assertIn("<script>window.__xss2=1</script>", text)
        self.assertIn('请讲<img src=x onerror="window.__xss3=1">一次',
                      modal.locator(".c-q").input_value())
        self.assertNotIn(KEY, text)

    # ----------------------------------------------------- (a) Draft-only block
    def test_draft_only_protocol_never_creates_a_structured_interview(self):
        created = self.post("/api/v1/projects", {"title": "Draft Only", "role_title": "Engineer"})
        pid = created["project_id"]
        self.patch(f"/api/v1/protocol-revisions/{created['draft_revision_id']}", {"payload": PROTOCOL})
        cid = self.post(f"/api/v1/projects/{pid}/candidates",
                        {"display_name": "Draft Person"})["candidate_id"]
        workspace = self.get(f"/api/v1/projects/{pid}/protocol-workspace")
        self.assertIsNone(workspace["current"])
        self.assertEqual(len(workspace["draft"]["criteria"]), 1)

        self.page.evaluate("pid => window.openProject(pid)", pid)
        self.open_step(cid)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".notice.danger")).to_be_visible()
        expect(modal.locator(".notice.danger")).to_contain_text("还没有已发布的岗位标准")
        self.assertEqual(modal.locator(".criterion-block").count(), 0)
        self.assertEqual(modal.get_by_role("button", name="保存").count(), 0)
        self.assertEqual(self.counts(cid)["events"], 0)

        # The same wall applies after a reload: nothing was cached into the form.
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_function("Boolean(window.openProject)")
        self.page.evaluate("pid => window.openProject(pid)", pid)
        self.open_step(cid)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        expect(self.page.locator(".modal .notice.danger")).to_be_visible()
        self.assertEqual(self.counts(cid)["events"], 0)

    def test_same_project_other_candidate_scorecard_is_refused_before_read(self):
        """A valid event for B must not open over A's visible candidate workspace."""
        other = self.post(f"/api/v1/projects/{self.pid}/candidates",
                          {"display_name": "Other Same-Project Person"})["candidate_id"]
        event_id, _ = self.schedule_interview(other, question="B 的真实面试问题")
        self.open_step(self.cid)
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text(
            "Synthetic Person")
        reads = []
        self.page.on("request", lambda request: reads.append(request.url)
                     if request.method == "GET" and request.url.endswith("/scorecards")
                     else None)
        self.page.evaluate(
            "args => window.openScorecards(args.cid, args.eid)",
            {"cid": other, "eid": event_id})
        modal = self.page.locator(".modal")
        expect(modal.locator(".notice.danger")).to_be_visible()
        expect(modal.locator(".notice.danger")).to_contain_text(
            "当前工作区候选人与面评目标不一致")
        self.assertEqual(modal.get_by_role("button", name="提交并锁定").count(), 0)
        self.assertEqual(reads, [], "mismatched drawer must not fetch another candidate's scorecard")
        self.assertEqual(self.counts(self.cid)["scorecards"], 0)
        self.assertEqual(self.counts(other)["scorecards"], 0)

    # ------------------------------------ (b) candidate ownership under switching
    def test_event_and_scorecard_stay_bound_to_the_opening_candidate(self):
        """Ownership survives a candidate switch and is refused when ids disagree.

        (1) A scorecard modal opened for B cannot be submitted after the
            workspace underneath switches to A; reopen B to submit safely.
        (2) A dashboard deep link whose candidate id and event id disagree is
            refused instead of silently scoring somebody else's interview.
        """
        other = self.post(f"/api/v1/projects/{self.pid}/candidates",
                          {"display_name": "Second Person"})["candidate_id"]
        event_id, _ = self.schedule_interview(other, question="B 的面试问题")
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="独立 Scorecard").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)

        # (1) switch the visible workspace to the other candidate mid-modal
        self.page.evaluate("cid => window.openCandidate(cid)", self.cid)
        expect(self.page.locator(".candidate-steps")).to_be_visible()
        modal.locator("#sc-evaluator").fill("面试官B")
        modal.locator(".c-obs").fill("只应归属第二个候选人")
        modal.locator(".c-rec").fill("advance")
        self.page.get_by_role("button", name="提交并锁定").click()
        expect(self.page.locator("#toast-root")).to_contain_text("已阻止提交")
        expect(self.page.locator("#modal-root .modal")).to_have_count(1)
        with closing(self.db()) as connection:
            rows = connection.execute(
                "SELECT candidate_id, event_id FROM interview_scorecard_submission").fetchall()
        self.assertEqual(rows, [], "switching candidate must not submit B while A is visible")
        self.assertEqual(self.counts(self.cid)["scorecards"], 0)

        # Reopen B's exact event and submit there: safety must not block valid HR work.
        self.page.evaluate("window.closeModal()")
        self.open_step(other, "面试")
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="独立 Scorecard").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        modal.locator("#sc-evaluator").fill("面试官B")
        modal.locator(".c-obs").fill("只应归属第二个候选人")
        modal.locator(".c-rec").fill("advance")
        self.page.get_by_role("button", name="提交并锁定").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with closing(self.db()) as connection:
            rows = connection.execute(
                "SELECT candidate_id, event_id FROM interview_scorecard_submission").fetchall()
        self.assertEqual(rows, [(other, event_id)])
        self.assertEqual(self.counts(self.cid)["scorecards"], 0)

        # (2) deep link with a mismatched candidate id must be refused
        before = self.counts(other)["scorecards"]
        scorecard_reads = []
        self.page.on("request", lambda r: scorecard_reads.append(r.url)
                     if r.url.endswith("/scorecards") else None)
        self.page.evaluate(
            "args => window.openOperationalItem('pending_interview_feedback', args.pid, args.cid, args.eid)",
            {"pid": self.pid, "cid": self.cid, "eid": event_id})
        mismatch = self.page.locator(".modal")
        expect(mismatch.locator(".notice.danger")).to_be_visible()
        expect(mismatch.locator(".notice.danger")).to_contain_text("不属于当前候选人")
        self.assertEqual(mismatch.get_by_role("button", name="提交并锁定").count(), 0)
        self.assertEqual([u for u in scorecard_reads if event_id in u], [],
                         "a refused ownership check must not read the other candidate's scorecards")
        self.assertEqual(self.counts(other)["scorecards"], before)

    # --------------------------------------------- (c) R1 open, R2 before submit
    def test_revision_change_while_the_form_is_open_blocks_the_write(self):
        self.open_step(self.cid)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        modal.locator(".c-q").fill("R1 提纲问题")

        revision = self.publish_next(self.pid, PROTOCOL_R2)
        self.assertTrue(revision)

        self.page.get_by_role("button", name="保存").click()
        expect(self.page.locator("#toast-root")).to_contain_text("岗位标准已更新")
        self.assertEqual(self.counts(self.cid)["events"], 0)
        self.assertEqual(self.counts(self.cid)["sources"], 1)

    # ------------------------------------- (d) historical R1 event after a R2 swap
    def test_historical_event_is_never_remapped_by_a_newer_revision(self):
        event_id, metadata = self.schedule_interview()
        before = self.counts(self.cid)
        self.publish_next(self.pid, PROTOCOL_R2)

        self.open_step(self.cid)
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="完成").first.click()
        modal = self.page.locator(".modal")
        expect(modal.locator(".notice.danger")).to_be_visible()
        expect(modal.locator(".notice.danger")).to_contain_text("已阻止提交")
        self.assertEqual(modal.get_by_role("button", name="完成").count(), 0)
        self.page.get_by_role("button", name="关闭").click()

        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="独立 Scorecard").click()
        scorecard_modal = self.page.locator(".modal")
        expect(scorecard_modal.locator(".notice")).to_be_visible()
        expect(scorecard_modal.locator(".notice")).to_contain_text("只读")
        self.assertEqual(scorecard_modal.get_by_role("button", name="提交并锁定").count(), 0)
        self.page.get_by_role("button", name="关闭").click()

        after = self.counts(self.cid)
        self.assertEqual(after, before)
        with closing(self.db()) as connection:
            stored = json.loads(connection.execute(
                "SELECT metadata_json FROM recruitment_event WHERE id=?", (event_id,)).fetchone()[0])
        self.assertEqual(stored, metadata)
        self.assertEqual(stored["questions"][0]["criterion_key"], KEY)
        self.assertNotIn(KEY_R2, json.dumps(stored, ensure_ascii=False))


    # ------------------------------------------------------------- S1b list UX
    def test_list_quick_schedule_targets_second_candidate_and_preserves_return(self):
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.locator("#cand-q").fill("Synthetic")
        self.page.get_by_role("button", name="应用筛选").click()
        row = self.page.locator(f'tr[data-candidate-id="{second}"]')
        expect(row).to_be_visible()
        before_a = self.counts(self.cid)
        row.locator('[data-quick-action="schedule"]').click()
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        modal = self.page.locator(".modal")
        expect(modal).to_contain_text("已发布标准")
        self.assertNotIn("criterion_key", modal.inner_text())
        modal.locator(".c-q").fill("第二位候选人的面试问题")
        modal.get_by_role("button", name="保存").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with closing(self.db()) as connection:
            rows = connection.execute(
                "SELECT candidate_id, metadata_json FROM recruitment_event "
                "WHERE candidate_id IN (?,?)", (self.cid, second)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], second)
        self.assertEqual(json.loads(rows[0][1])["questions"][0]["criterion_key"], KEY)
        self.assertEqual(self.counts(self.cid), before_a)
        expect(self.page.locator("#top-back")).to_be_visible()
        self.page.locator("#top-back").click()
        expect(self.page.locator("#cand-q")).to_have_value("Synthetic")
        expect(self.page.locator(f'tr[data-candidate-id="{second}"]')).to_be_visible()

    def test_list_quick_scorecard_uses_exact_candidate_event_and_persists(self):
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        published = self.get(f"/api/v1/projects/{self.pid}/protocol-workspace")
        event = self.post(f"/api/v1/candidates/{second}/events", {
            "event_type": "interview", "event_state": "scheduled",
            "title": "Second interview", "metadata": {
                "protocol_revision_id": published["current_revision_id"],
                "questions": [{"criterion_key": KEY, "question": "核实经历"}]}})
        before_a = self.counts(self.cid)
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.locator(f'tr[data-candidate-id="{second}"] [data-quick-action="scorecard"]').click()
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        modal = self.page.locator(".modal")
        expect(modal.locator("#sc-evaluator")).to_be_visible()
        self.assertNotIn("criterion_key", modal.inner_text())
        modal.locator("#sc-evaluator").fill("独立面试官")
        modal.locator(".c-obs").fill("仅属于第二位候选人的观察")
        modal.locator("#sc-rec").fill("advance")
        # Negative: a stale callback for a second interview must not reuse
        # this visible first-event form, even when both share Published keys.
        other_event = self.post(f"/api/v1/candidates/{second}/events", {
            "event_type": "interview", "event_state": "scheduled",
            "title": "Different interview", "metadata": {
                "protocol_revision_id": published["current_revision_id"],
                "questions": [{"criterion_key": KEY, "question": "不同面试"}]}})
        before_wrong = self.counts(second)
        self.page.evaluate("args => window.saveScorecard(args.cid,args.eid)",
                           {"cid": second, "eid": other_event["event_id"]})
        expect(self.page.locator("#toast-root")).to_contain_text("面评窗口与目标候选人/事件不一致")
        self.assertEqual(self.counts(second), before_wrong)
        expect(modal).to_be_visible()
        modal.get_by_role("button", name="提交并锁定").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with closing(self.db()) as connection:
            rows = connection.execute(
                "SELECT candidate_id,event_id,feedback_json FROM interview_scorecard_submission "
                "WHERE candidate_id IN (?,?)", (self.cid, second)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][0], rows[0][1]), (second, event["event_id"]))
        self.assertEqual(json.loads(rows[0][2])[0]["criterion_key"], KEY)
        self.assertEqual(self.counts(self.cid), before_a)
        expect(self.page.locator("#top-back")).to_be_visible()
        self.page.locator("#top-back").click()
        # A second event now exists. The list shortcut must refuse to guess
        # which interview to reopen; select the original event in the UI.
        row = self.page.locator(f'tr[data-candidate-id="{second}"]')
        row.get_by_role("button", name="打开工作台").click()
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        original = self.page.locator(f'[data-event-id="{event["event_id"]}"]')
        expect(original).to_be_visible()
        original.get_by_role("button", name="独立 Scorecard").click()
        expect(self.page.locator(".modal")).to_contain_text("仅属于第二位候选人的观察")

    def test_list_quick_actions_do_not_write_when_no_interview_exists(self):
        self.page.evaluate("window.setProjectTab('candidates')")
        before = self.counts(self.cid)
        row = self.page.locator(f'tr[data-candidate-id="{self.cid}"]')
        row.locator('[data-quick-action="scorecard"]').click()
        expect(self.page.locator("#toast-root")).to_contain_text("尚无可填写面评的面试记录")
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Person")
        self.assertEqual(self.counts(self.cid), before)
        expect(self.page.locator("#top-back")).to_be_visible()
        self.page.locator("#top-back").click()
        row = self.page.locator(f'tr[data-candidate-id="{self.cid}"]')
        row.locator('[data-quick-action="verify"]').click()
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Person")
        expect(self.page.locator(".candidate-step.active")).to_contain_text("资料")
        self.assertEqual(self.counts(self.cid), before)


    def test_list_multiple_interviews_never_guesses_an_event_id(self):
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        published = self.get(f"/api/v1/projects/{self.pid}/protocol-workspace")
        for label in ("Interview One", "Interview Two"):
            self.post(f"/api/v1/candidates/{second}/events", {
                "event_type": "interview", "event_state": "scheduled",
                "title": label, "metadata": {
                    "protocol_revision_id": published["current_revision_id"],
                    "questions": [{"criterion_key": KEY, "question": label}]}})
        before = self.counts(second)
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.locator(f'tr[data-candidate-id="{second}"] [data-quick-action="scorecard"]').click()
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        expect(self.page.locator("#toast-root")).to_contain_text("有多场面试")
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        self.assertEqual(self.counts(second), before)

    def test_delayed_list_quick_action_never_replaces_newer_candidate_form(self):
        """A delayed A summary cannot displace B's unsaved interview form."""
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        self.page.locator("#top-back").click()
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.locator(f'tr[data-candidate-id="{second}"]').wait_for()
        self.page.evaluate("""cid => {
          const originalFetch = window.fetch.bind(window);
          const originalAction = window.openCandidateQuickAction;
          window.__oldQuickHeld = false;
          window.__oldQuickDone = false;
          window.fetch = async (...args) => {
            if (!window.__oldQuickHeld &&
                String(args[0]).includes('/api/v1/candidates/' + cid + '/summary')) {
              window.__oldQuickHeld = true;
              await new Promise(resolve => { window.__releaseOldQuick = resolve; });
            }
            return originalFetch(...args);
          };
          window.openCandidateQuickAction = (id, kind) => {
            const pending = originalAction(id, kind);
            if (id === cid) pending.finally(() => { window.__oldQuickDone = true; });
            return pending;
          };
        }""", self.cid)
        self.page.locator(
            f'tr[data-candidate-id="{self.cid}"] [data-quick-action="schedule"]').click()
        self.page.wait_for_function("window.__oldQuickHeld === true")
        self.page.locator(
            f'tr[data-candidate-id="{second}"] [data-quick-action="schedule"]').click()
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        modal = self.page.locator("#modal-root .modal")
        expect(modal.locator("h3")).to_have_text("新增结构化面试")
        modal.locator("#e-title").fill("B 的未保存面试")
        self.page.evaluate("window.__releaseOldQuick()")
        self.page.wait_for_function("window.__oldQuickDone === true")
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        expect(modal.locator("#e-title")).to_have_value("B 的未保存面试")
        self.assertEqual(self.counts(self.cid)["events"], 0)
        self.assertEqual(self.counts(second)["events"], 0)

    def test_delayed_interview_protocol_cannot_open_stale_modal(self):
        """A delayed Published GET cannot overwrite B's workspace or a later form."""
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        self.page.evaluate("""pid => {
          const originalFetch = window.fetch.bind(window);
          const originalEvent = window.openEvent;
          window.__oldEventHeld = false;
          window.__oldEventDone = false;
          window.fetch = async (...args) => {
            if (!window.__oldEventHeld &&
                String(args[0]).includes('/api/v1/projects/' + pid + '/protocol-workspace')) {
              window.__oldEventHeld = true;
              await new Promise(resolve => { window.__releaseOldEvent = resolve; });
            }
            return originalFetch(...args);
          };
          window.openEvent = (cid, type) => {
            const pending = originalEvent(cid, type);
            pending.finally(() => { window.__oldEventDone = true; });
            return pending;
          };
        }""", self.pid)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        self.page.wait_for_function("window.__oldEventHeld === true")
        self.page.evaluate("cid => window.openCandidate(cid)", second)
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        self.page.evaluate("window.__releaseOldEvent()")
        self.page.wait_for_function("window.__oldEventDone === true")
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        self.assertEqual(self.counts(self.cid)["events"], 0)
        self.assertEqual(self.counts(second)["events"], 0)

        # The project-level flow remains a supported legitimate entry.
        self.page.locator("#top-back").click()
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.evaluate("window.setCandidateView('flow')")
        self.page.get_by_role("button", name="＋ 面试排期").click()
        expect(self.page.locator("#modal-root .modal h3")).to_have_text("新增结构化面试")

    def test_delayed_interview_save_never_uses_another_candidate_form(self):
        """An A save held in Published GET must not read or write B's later modal."""
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        self.open_step(self.cid)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        expect(self.page.locator("#modal-root .modal .criterion-block")).to_have_count(1)
        self.page.locator("#e-title").fill("A original draft")
        self.page.evaluate("""pid => {
          const originalFetch = window.fetch.bind(window);
          const originalSave = window.saveEvent;
          window.__oldSaveHeld = false;
          window.__oldSaveDone = false;
          window.__holdSaveOnce = true;
          window.fetch = async (...args) => {
            if (window.__holdSaveOnce &&
                String(args[0]).includes('/api/v1/projects/' + pid + '/protocol-workspace')) {
              window.__holdSaveOnce = false;
              window.__oldSaveHeld = true;
              await new Promise(resolve => { window.__releaseOldSave = resolve; });
            }
            return originalFetch(...args);
          };
          window.saveEvent = (cid, type) => {
            const pending = originalSave(cid, type);
            pending.finally(() => { window.__oldSaveDone = true; });
            return pending;
          };
        }""", self.pid)
        self.page.get_by_role("button", name="保存").click()
        self.page.wait_for_function("window.__oldSaveHeld === true")
        self.page.evaluate("window.closeModal()")
        self.open_step(second)
        self.page.get_by_role("button", name="＋ 面试排期").click()
        modal = self.page.locator("#modal-root .modal")
        expect(modal.locator("h3")).to_have_text("新增结构化面试")
        modal.locator("#e-title").fill("B unsaved draft")
        modal.locator(".c-q").fill("B unsaved question")
        self.page.evaluate("window.__releaseOldSave()")
        self.page.wait_for_function("window.__oldSaveDone === true")
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        expect(modal.locator("#e-title")).to_have_value("B unsaved draft")
        expect(modal.locator(".c-q")).to_have_value("B unsaved question")
        self.assertEqual(self.counts(self.cid)["events"], 0,
                         "A must not receive B's unsaved fields")
        self.assertEqual(self.counts(second)["events"], 0)

    def test_delayed_completion_save_never_uses_other_candidate_feedback(self):
        """A completion waiting for Core must not PATCH A with B's feedback."""
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        event_a, _ = self.schedule_interview(self.cid)
        event_b, _ = self.schedule_interview(second)
        self.open_step(self.cid)
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="完成").first.click()
        modal = self.page.locator("#modal-root .modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        modal.locator(".c-obs").fill("A own feedback")
        self.page.evaluate("""cid => {
          const originalFetch = window.fetch.bind(window);
          const originalSave = window.saveEventCompletion;
          window.__oldCompletionHeld = false;
          window.__oldCompletionDone = false;
          window.__holdCompletionOnce = true;
          window.fetch = async (...args) => {
            if (window.__holdCompletionOnce &&
                String(args[0]).includes('/api/v1/candidates/' + cid + '/events')) {
              window.__holdCompletionOnce = false;
              window.__oldCompletionHeld = true;
              await new Promise(resolve => { window.__releaseOldCompletion = resolve; });
            }
            return originalFetch(...args);
          };
          window.saveEventCompletion = (cid, id, plain) => {
            const pending = originalSave(cid, id, plain);
            pending.finally(() => { window.__oldCompletionDone = true; });
            return pending;
          };
        }""", self.cid)
        self.page.get_by_role("button", name="完成").last.click()
        self.page.wait_for_function("window.__oldCompletionHeld === true")
        self.page.evaluate("window.closeModal()")
        self.open_step(second)
        self.page.locator(".timeline-item").filter(has_text="面试").get_by_role(
            "button", name="完成").first.click()
        modal = self.page.locator("#modal-root .modal")
        expect(modal.locator(".criterion-block")).to_have_count(1)
        modal.locator(".c-obs").fill("B unsaved feedback")
        self.page.evaluate("window.__releaseOldCompletion()")
        self.page.wait_for_function("window.__oldCompletionDone === true")
        expect(self.page.locator(".candidate-workspace-head h1")).to_have_text("Synthetic Second")
        expect(modal.locator(".c-obs")).to_have_value("B unsaved feedback")
        with closing(self.db()) as connection:
            rows = connection.execute(
                "SELECT id, event_state, metadata_json FROM recruitment_event "
                "WHERE id IN (?, ?)", (event_a, event_b)).fetchall()
        self.assertEqual(len(rows), 2)
        for eid, status, metadata in rows:
            self.assertEqual(status, "scheduled", eid)
            self.assertFalse(json.loads(metadata).get("feedback"), eid)

    def test_list_stale_archived_row_is_blocked_by_fresh_core_summary(self):
        second = self.post(f"/api/v1/projects/{self.pid}/candidates",
                           {"display_name": "Synthetic Second"})["candidate_id"]
        self.page.evaluate("window.setProjectTab('candidates')")
        row = self.page.locator(f'tr[data-candidate-id="{second}"]')
        expect(row.locator('[data-quick-action="schedule"]')).to_be_visible()
        self.post(f"/api/v1/candidates/{second}/archive", {})
        before = self.counts(second)
        row.locator('[data-quick-action="schedule"]').click()
        expect(self.page.locator("#toast-root")).to_contain_text("已归档")
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        self.assertEqual(self.counts(second), before)



if __name__ == "__main__":
    unittest.main()
