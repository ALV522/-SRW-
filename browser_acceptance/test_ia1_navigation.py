"""IA-1 acceptance: three sidebar entries, three project tabs, legacy deep links.

Real Chromium against a disposable loopback Core. The contract under test
(issue #215): the navigation surface shrinks from 6 + 8 to 3 + 3, but every
former page stays reachable - old tab keys, deep links and
openOperationalItem must land on real content instead of an empty shell.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from contextlib import closing
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEXT = "Synthetic candidate led a cross-team launch; the launch shipped on time."

PROTOCOL = {
    "brief": {"title": "Backend Engineer", "summary": "Synthetic requisition"},
    "criteria": [{
        "criterion_key": "comm", "name": "沟通能力", "definition": "跨部门沟通",
        "decision_critical": True, "verification_required": False,
        "verification_probes": ["有没有相关经历"], "weight": 1,
    }],
    "assessment_stages": [
        {"stage_key": "resume", "name": "简历筛选", "criteria": ["comm"]},
        {"stage_key": "interview", "name": "面试", "criteria": ["comm"]},
    ],
    "decision_policy": {"human_final": True},
}


class IANavigationBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="srw-browser-ia1-",
                                               ignore_cleanup_errors=True)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        env = {**os.environ, "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
               "RECRUITMENT_SESSION_ENFORCE": "0", "SRW_BACKGROUND_WORKER": "0"}
        cls.server = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "browser_acceptance" / "serve.py"),
             "--workspace", cls.temp.name, "--port", str(cls.port)],
            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(150):
            try:
                urllib.request.urlopen(cls.base + "/health/ready", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        cls.pid, cls.cid = cls.seed()

        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page(viewport={"width": 1440, "height": 980}, locale="zh-CN")
        cls.errors = []
        cls.page.on("pageerror", lambda exc: cls.errors.append(str(exc)))
        cls.page.goto(cls.base + "/v1", wait_until="domcontentloaded")
        cls.page.wait_for_function("Boolean(window.openProject)")
        cls.page.wait_for_selector("#content .kpi-card", timeout=20000)
        cls.page.wait_for_timeout(400)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
        finally:
            cls._pw.stop()
            cls.server.terminate()
            try:
                cls.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server.kill()
            time.sleep(0.4)
            cls.temp.cleanup()

    # ------------------------------------------------------------------ helpers
    @classmethod
    def call(cls, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(cls.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())

    @classmethod
    def seed(cls):
        project = cls.call("POST", "/api/v1/projects",
                           {"title": "Synthetic Project", "role_title": "Backend Engineer"})
        pid = project["project_id"]
        cls.call("PATCH", f"/api/v1/protocol-revisions/{project['draft_revision_id']}",
                 {"payload": PROTOCOL})
        cls.call("POST", f"/api/v1/protocol-revisions/{project['draft_revision_id']}/publish", {})
        cid = cls.call("POST", f"/api/v1/projects/{pid}/candidates",
                       {"display_name": "Synthetic Person"})["candidate_id"]
        cls.call("POST", f"/api/v1/candidates/{cid}/sources/text",
                 {"text_content": TEXT, "publish_material": True})
        return pid, cid

    def open_project(self):
        page = self.page
        page.evaluate("window.go('projects')")
        page.wait_for_selector("text=Synthetic Project")
        page.evaluate("pid => window.openProject(pid)", self.pid)
        page.wait_for_selector(".project-banner")
        page.wait_for_timeout(300)

    def active_tab(self):
        tab = self.page.locator(".tabs .tab.active")
        return tab.inner_text().strip() if tab.count() else ""

    def tab_body(self):
        return self.page.locator("#project-tab-body").inner_text()

    # ------------------------------------------------------------------- tests
    def test_01_sidebar_is_three_entry_points(self):
        labels = [x.replace("\n", "").strip() for x in self.page.locator(".nav-item").all_inner_texts()]
        self.assertEqual(self.page.locator(".nav-item").count(), 3, labels)
        self.assertEqual([l.replace("▦", "").replace("▣", "").replace("⚙", "").strip() for l in labels],
                         ["今日待办", "招聘项目", "设置"])

    def test_02_settings_reaches_templates_knowledge_and_tasks(self):
        page = self.page
        page.evaluate("window.go('settings')")
        page.wait_for_selector("#content section.panel")
        cards = [t.strip() for t in page.locator("#content section.panel .provider-card h3").all_inner_texts()]
        self.assertEqual(cards, ["岗位模板", "知识库", "后台任务", "运行诊断"])
        # the hidden pages stay live and keep 设置 highlighted
        page.get_by_role("button", name="进入岗位模板").click()
        page.wait_for_selector("#content h1")
        self.assertIn("岗位模板", page.locator("#content h1").inner_text())
        self.assertEqual(page.locator(".nav-item.active").count(), 1)
        self.assertIn("设置", page.locator(".nav-item.active").inner_text())
        self.assertEqual(page.locator("#top-title").inner_text(), "设置 · 岗位模板")

    def test_03_project_exposes_three_tabs(self):
        self.open_project()
        tabs = [t.strip() for t in self.page.locator(".tabs .tab").all_inner_texts()]
        self.assertEqual(tabs, ["概览", "岗位与标准", "候选人"])
        self.assertEqual(self.active_tab(), "概览")
        # 概览 keeps the former cockpit + audit capabilities on the same page
        expect(self.page.locator("#ov-cockpit")).to_be_visible()
        expect(self.page.locator("#ov-audit")).to_be_visible()
        self.assertNotIn("加载失败", self.tab_body())

    def test_04_legacy_tabs_still_reach_real_content(self):
        self.open_project()
        expected = {
            "cockpit": ("概览", None),
            "audit": ("概览", None),
            "flow": ("候选人", "面试"),
            "ops": ("候选人", "待办"),
            "quality": ("候选人", "数据质量"),
        }
        for key, (tab, view) in expected.items():
            self.page.evaluate("k => window.setProjectTab(k)", key)
            self.page.wait_for_timeout(1200)
            self.assertEqual(self.active_tab(), tab, key)
            body = self.tab_body()
            self.assertTrue(body.strip(), key)
            self.assertNotIn("加载失败", body, key)
            if view:
                self.assertIn(view, body, key)
        self.assertEqual(self.errors, [], self.errors[:3])

    def test_05_candidate_to_interview_save_click_count(self):
        """IA-1 does not shorten this path on purpose; IA-2 owns the inline form.

        The measured budget is 4 clicks (row action, 面试 step, ＋面试排期, 保存).
        """
        self.open_project()
        self.page.evaluate("window.setProjectTab('candidates')")
        self.page.wait_for_selector("tbody tr")
        clicks = 0
        row = self.page.locator("tbody tr").filter(has_text="Synthetic Person")
        row.locator("button.btn.primary").click()
        clicks += 1
        self.page.wait_for_selector(".candidate-steps")
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        clicks += 1
        self.page.get_by_role("button", name="＋ 面试排期").click()
        clicks += 1
        self.page.wait_for_selector("#modal-root .modal")
        self.page.locator("#e-title").fill("合成技术面")
        self.page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
        clicks += 1
        self.page.wait_for_selector("#modal-root .modal", state="detached", timeout=20000)
        self.assertEqual(clicks, 4)
        events = self.call("GET", f"/api/v1/candidates/{self.cid}/events")["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_state"], "scheduled")


    def test_06_pending_feedback_deep_link_targets_the_right_candidate(self):
        """The deep link must win over the default "first candidate" selection.

        The target is chosen from the real search order (the second entry), so
        the assertion cannot pass by accident when the link target happens to
        be the first row. The opened Scorecard must belong to that target, and
        switching the in-page selector must never open the candidate drawer.
        """
        page = self.page
        self.call("POST", f"/api/v1/projects/{self.pid}/candidates",
                  {"display_name": "Second Person"})
        order = [c["candidate_id"] for c in self.call(
            "GET", f"/api/v1/projects/{self.pid}/candidate-search?q=&limit=20")["candidates"]]
        self.assertGreaterEqual(len(order), 2, order)
        first, target = order[0], order[1]
        self.assertNotEqual(first, target)

        events = self.call("GET", f"/api/v1/candidates/{target}/events")["events"]
        if not events:
            # schedule through the UI so the event carries its pinned revision;
            # an API-only event without a pin is read-only by design
            page.evaluate("cid => window.openCandidate(cid)", target)
            page.wait_for_selector(".candidate-steps")
            page.locator(".candidate-step").filter(has_text="面试").click()
            page.get_by_role("button", name="＋ 面试排期").click()
            page.wait_for_selector("#modal-root .modal")
            page.locator("#e-title").fill("Target 面试")
            page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
            page.wait_for_selector("#modal-root .modal", state="detached", timeout=20000)
            events = self.call("GET", f"/api/v1/candidates/{target}/events")["events"]
        self.assertTrue(events, "the deep-link target needs a scheduled interview")
        event_id = events[0]["event_id"]
        before_other = len(self.call("GET", f"/api/v1/candidates/{first}/events")["events"])

        self.open_project()
        page.evaluate(
            "args => window.openOperationalItem('pending_interview_feedback', args.pid, args.cid, args.eid)",
            {"pid": self.pid, "cid": target, "eid": event_id})
        page.wait_for_selector("#project-tab-body .searchbar select", timeout=20000)
        selector = page.locator("#project-tab-body .searchbar select")
        expect(selector).to_have_value(target)
        self.assertEqual(self.active_tab(), "候选人")
        expect(page.locator(".candidate-workspace-page")).to_have_count(0)

        modal = page.locator("#modal-root .modal")
        expect(modal).to_be_visible()
        modal.locator("#sc-evaluator").fill("面试官B")
        modal.locator(".c-obs").fill("只属于深链目标候选人")
        modal.locator(".c-rec").fill("advance")
        page.get_by_role("button", name="提交并锁定").click()
        page.wait_for_selector("#modal-root .modal", state="detached", timeout=20000)
        self.assertEqual(len(self.call("GET", f"/api/v1/events/{event_id}/scorecards")["scorecards"]), 1)
        self.assertEqual(len(self.call("GET", f"/api/v1/candidates/{first}/events")["events"]), before_other)

        # switching the in-page selector stays in the interview view (no drawer)
        page.select_option("#project-tab-body .searchbar select", first)
        page.wait_for_selector("#project-tab-body .searchbar select")
        expect(page.locator("#project-tab-body .searchbar select")).to_have_value(first)
        expect(page.locator(".candidate-workspace-page")).to_have_count(0)
        self.assertEqual(self.active_tab(), "候选人")
        self.assertNotIn("加载失败", self.tab_body())


    def test_07_other_sections_have_no_stale_project_back_action(self):
        """#235: leaving a project must not show a misleading project return.

        The main branch has no topbar back button; a new topbar must not
        expose the stale projectId when navigating to other top-level pages.
        This is a UI-only check, with no business mutation or auto-selection.
        """
        page = self.page
        for destination, title in (("dashboard", "今日待办"), ("settings", "设置")):
            with self.subTest(destination=destination):
                self.open_project()
                page.evaluate("p => window.go(p)", destination)
                expect(page.locator("#top-title")).to_have_text(title)
                self.assertEqual(
                    page.locator("#top-back:visible").count(), 0,
                    f"{destination}: back must not point to a previous project",
                )
                self.assertEqual(
                    page.locator("#top-crumb .crumb-link").count(), 0,
                    f"{destination}: stale project/candidate breadcrumb",
                )
                self.assertEqual(page.locator(".nav-item.active").count(), 1)
                self.assertIn(title, page.locator(".nav-item.active").inner_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
