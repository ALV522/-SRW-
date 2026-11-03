"""#43 M3A real Chromium: an ON Local Browser can pair and use the same Core.

The one-time code is obtained directly from the synthetic in-process Core,
never written to stdout, a URL, a file, or a CI artifact. This does not test
the production TTY delivery channel (covered by test_start_local_web), WPF,
external Browser attachment, or M3B shared-Host lifecycle.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "backend", ROOT / "convergence_tests"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from knowledge_fixture import create_minimal_knowledge_tree  # noqa: E402
from srw.api.app import create_v1_app  # noqa: E402


class BusinessSessionOnBrowserAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="srw-session-on-browser-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self.database = self.data / "srw_v1.db"
        previous = os.environ.get("RECRUITMENT_SESSION_ENFORCE")
        os.environ["RECRUITMENT_SESSION_ENFORCE"] = "1"

        def restore_env():
            if previous is None:
                os.environ.pop("RECRUITMENT_SESSION_ENFORCE", None)
            else:
                os.environ["RECRUITMENT_SESSION_ENFORCE"] = previous

        self.addCleanup(restore_env)
        app = create_v1_app(
            f"sqlite+pysqlite:///{self.database.as_posix()}",
            data_dir=self.data, knowledge_dir=knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )
        self.assertIsNotNone(app.state.business_gateway)
        self.code = app.state.business_gateway.issue_pairing_code()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"

        import uvicorn
        self.server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="error",
            access_log=False, lifespan="on",
        ))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        for _ in range(150):
            if not self.thread.is_alive():
                self.fail("synthetic ON Core exited before readiness")
            try:
                with urllib.request.urlopen(self.base + "/health/ready", timeout=0.4) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        else:
            self.fail("synthetic ON Core did not become ready")

        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(locale="zh-CN")
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def stop_server(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)
        self.assertFalse(self.thread.is_alive(), "synthetic ON Core did not stop")

    def count_projects(self) -> int:
        with sqlite3.connect(self.database) as connection:
            return connection.execute("SELECT COUNT(*) FROM project").fetchone()[0]

    def test_pairing_unlocks_real_ui_and_csrf_protects_writes(self) -> None:
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        expect(self.page.get_by_role("heading", name="本机配对")).to_be_visible()
        self.assertEqual(self.context.request.get(self.base + "/api/v1/projects").status, 401)
        self.assertEqual(self.count_projects(), 0)

        self.page.get_by_label("一次性配对码").fill("incorrect-synthetic-code")
        self.page.get_by_role("button", name="连接工作台").click()
        expect(self.page.get_by_role("alert")).to_contain_text("配对失败")
        self.assertEqual(self.count_projects(), 0)

        self.page.get_by_label("一次性配对码").fill(self.code)
        self.page.get_by_role("button", name="连接工作台").click()
        expect(self.page.locator("#content h1")).to_have_text("工作台总览")
        self.assertNotIn("srw_business_session=", self.page.evaluate("document.cookie"))
        self.assertIn("srw_csrf=", self.page.evaluate("document.cookie"))

        # A valid cookie without the independent CSRF header must not write.
        denied = self.page.evaluate("""async () => {
          const r = await fetch('/api/v1/projects', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title:'denied',role_title:'Synthetic'}),
          });
          return r.status;
        }""")
        self.assertEqual(denied, 403)
        self.assertEqual(self.count_projects(), 0)

        self.page.get_by_role("button", name="＋ 新建招聘项目").click()
        self.page.locator("#np-title").fill("synthetic paired recruitment")
        self.page.locator("#np-role").fill("Analyst")
        self.page.get_by_role("button", name="创建并进入项目").click()
        expect(self.page.get_by_role("button", name="四步建岗向导")).to_be_visible()
        self.assertEqual(self.count_projects(), 1)

        # Revocation must immediately deny reads and cause a new pairing prompt.
        status = self.page.evaluate("""async () => {
          const r = await fetch('/api/v1/runtime/business-logout',
            window.srwAuthInit({method:'POST'}));
          return r.status;
        }""")
        self.assertEqual(status, 200)
        self.assertEqual(self.context.request.get(self.base + "/api/v1/projects").status, 401)
        self.page.reload(wait_until="domcontentloaded")
        expect(self.page.get_by_role("heading", name="本机配对")).to_be_visible()
        self.assertEqual(self.errors, [], self.errors)


if __name__ == "__main__":
    unittest.main()
