"""#240 UX-2a: real browser, real disposable Core, read-only project resume shortcut.

This validates one explicit home-to-project click without guessing any candidate,
event, scorecard or human decision. It is not #240's full 9-to-6-click proof,
and it is not Windows WPF/Native acceptance.
"""
from __future__ import annotations

import os
import socket
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


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DashboardProjectResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="srw-home-resume-")
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = {**os.environ, "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
               "RECRUITMENT_SESSION_ENFORCE": "0", "SRW_BACKGROUND_WORKER": "0"}
        cls.server = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "browser_acceptance" / "serve.py"),
             "--workspace", cls.temp.name, "--port", str(cls.port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if cls.server.poll() is not None:
                    raise RuntimeError("Synthetic project-resume Core exited early")
                try:
                    with urllib.request.urlopen(cls.base + "/health/ready", timeout=0.5) as resp:
                        if resp.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Synthetic project-resume Core not ready")
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
        self.context = self.browser.new_context(locale="zh-CN",
                                                viewport={"width": 1440, "height": 900})
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)
        self.errors = []
        self.page.on("pageerror", lambda err: self.errors.append(str(err)))

    def tearDown(self):
        self.assertFalse(self.errors, self.errors)
        self.context.close()

    def create_project(self, title):
        response = self.page.request.post(
            self.base + "/api/v1/projects",
            data={"title": title, "role_title": "合成研究员"})
        self.assertEqual(response.status, 200, response.text()[:400])
        return response.json()["project_id"]

    def test_one_real_click_from_home_to_exact_project_workbench(self):
        project_id = self.create_project("UX2a Resume Sentinel")
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        expect(self.page.locator("#top-title")).to_have_text("今日待办")
        button = self.page.get_by_role(
            "button", name="进入工作区 · UX2a Resume Sentinel")
        expect(button).to_be_visible()
        self.assertEqual(self.page.locator("#dashboard-project-resume .resume-entry").count(), 1)
        # One deliberate operator click: no projects index / project row detour.
        clicks = []
        button.click()
        clicks.append("首页→准确项目工作区")
        expect(self.page.locator(".project-banner")).to_contain_text("UX2a Resume Sentinel")
        expect(self.page.locator("#project-next-action")).to_be_visible()
        self.assertEqual(len(clicks), 1)
        self.assertEqual(self.page.locator(".candidate-workspace-page").count(), 0)
        self.assertFalse(self.page.locator("#modal-root .modal").count())
        # Project identity comes from Core and is not recovered by guessing IDs.
        fetched = self.page.request.get(self.base + "/api/v1/projects").json()
        self.assertIn(project_id, {p["project_id"] for p in fetched["projects"]})

    def test_client_projection_excludes_archives_duplicates_and_missing_ids(self):
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        result = self.page.evaluate("""async () => {
          const { selectResumeProjects } = await import('/v1/task-resume-ui.js');
          return selectResumeProjects([
            {project_id:'a', title:'A', status:'open'},
            {project_id:'a', title:'Duplicate', status:'open'},
            {project_id:'archived', title:'Archived', status:'archived'},
            {project_id:'', title:'Missing', status:'open'},
            {project_id:'b', title:'B', status:'draft'},
            {project_id:'c', title:'C', status:'open'},
            {project_id:'d', title:'D', status:'open'},
            {project_id:'e', title:'E', status:'open'},
          ]);
        }""")
        self.assertEqual([(p["id"], p["title"]) for p in result],
                         [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")])


if __name__ == "__main__":
    unittest.main()
