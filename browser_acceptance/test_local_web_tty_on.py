"""#43: real Local Web launcher -> trusted PTY -> ON Chromium -> Core/SQLite.

Unlike the in-process M3A test, this starts the actual local-web launcher in a
new process. A synthetic one-time code is read only from a private PTY; it is
never emitted in assertion text, URLs, screenshots or CI logs. This is not
Windows WPF or shared-Core dual-carrier acceptance.
"""
from __future__ import annotations

import os
import re
import select
import signal
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


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX PTY launcher contract")
class LocalWebTtySessionOnAcceptance(unittest.TestCase):
    def test_sigterm_after_http_ready_releases_workspace_lease(self) -> None:
        # A default SIGTERM action kills the process before the outer lease
        # context exits if Uvicorn replays the signal on Server.run teardown.
        # This is a real launcher/HTTP/SQLite process, not a mocked signal.
        with tempfile.TemporaryDirectory(prefix="srw-sigterm-lease-") as temp:
            workspace = Path(temp) / "isolated-web-workspace"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(os.environ)
            env.update({
                "RECRUITMENT_SESSION_ENFORCE": "0",
                "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            })
            proc = subprocess.Popen(
                [sys.executable, "-B", str(ROOT / "scripts" / "start_local_web.py"),
                 "--workspace", str(workspace), "--synthetic",
                 "--no-browser", "--port", str(port)],
                cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            lease = workspace / "data" / "app.lock"
            try:
                for _ in range(120):
                    self.assertIsNone(proc.poll(), "launcher exited before readiness")
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health/ready", timeout=0.5
                        ) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(0.1)
                else:
                    self.fail("launcher never became HTTP ready")
                self.assertTrue(lease.is_dir(), "must hold a live workspace lease")
                proc.send_signal(signal.SIGTERM)
                self.assertEqual(proc.wait(timeout=15), 0,
                                 "SIGTERM must unwind through lease cleanup")
                self.assertFalse(lease.exists(),
                                 "SIGTERM exit left a stale authoritative app.lock")
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)

    def test_real_launcher_pairs_browser_without_leaking_code(self) -> None:
        import pty

        with tempfile.TemporaryDirectory(prefix="srw-tty-on-browser-") as temp:
            workspace = Path(temp) / "isolated-web-workspace"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            env = dict(os.environ)
            env.update({
                "RECRUITMENT_SESSION_ENFORCE": "1",
                "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            })
            env.pop("RECRUITMENT_SESSION_TOKEN", None)
            master, slave = pty.openpty()
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-B", str(ROOT / "scripts" / "start_local_web.py"),
                     "--workspace", str(workspace), "--synthetic",
                     "--no-browser", "--port", str(port)],
                    cwd=str(ROOT), env=env, stdin=slave, stdout=slave, stderr=slave,
                    start_new_session=True,
                )
            finally:
                os.close(slave)

            try:
                # Read the credential only from the private PTY, never from a
                # redirected stdout pipe, URL, subprocess error or test log.
                output = b""
                code = None
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        self.fail("Local Web launcher exited before PTY pairing")
                    ready, _, _ = select.select([master], [], [], 0.25)
                    if ready:
                        try:
                            output += os.read(master, 4096)
                        except OSError:
                            self.fail("PTY closed before a pairing code was issued")
                        match = re.search(
                            rb"PAIRING CODE \(single use, [0-9]+s\): ([A-Za-z0-9_-]{24,})",
                            output,
                        )
                        if match:
                            code = match.group(1).decode("ascii")
                            break
                self.assertIsNotNone(code, "trusted terminal did not receive a code")
                self.assertEqual(output.count(code.encode("ascii")), 1)

                for _ in range(120):
                    if proc.poll() is not None:
                        self.fail("Local Web launcher exited before HTTP readiness")
                    try:
                        with urllib.request.urlopen(base + "/health/ready", timeout=0.5) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(0.1)
                else:
                    self.fail("real Local Web launcher did not become ready")

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        context = browser.new_context(locale="zh-CN")
                        page = context.new_page()
                        page.goto(base + "/v1", wait_until="domcontentloaded")
                        expect(page.get_by_role("heading", name="本机配对")).to_be_visible()
                        self.assertEqual(context.request.get(base + "/api/v1/projects").status, 401)
                        self.assertNotIn(code, page.url)
                        self.assertNotIn(code, page.content())

                        page.get_by_label("一次性配对码").fill(code)
                        page.get_by_role("button", name="连接工作台").click()
                        expect(page.locator("#content h1")).to_have_text("今日待办")
                        self.assertNotIn("srw_business_session=", page.evaluate("document.cookie"))
                        self.assertIn("srw_csrf=", page.evaluate("document.cookie"))

                        # A paired cookie without the separate CSRF header
                        # cannot mutate the authoritative SQLite workspace.
                        denied = page.evaluate("""async () => {
                          const response = await fetch('/api/v1/projects', {
                            method:'POST', credentials:'same-origin',
                            headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({title:'denied',role_title:'Analyst'}),
                          });
                          return response.status;
                        }""")
                        self.assertEqual(denied, 403)
                        page.get_by_role("button", name="＋ 新建招聘项目").click()
                        page.locator("#np-title").fill("synthetic terminal-paired project")
                        page.locator("#np-role").fill("Analyst")
                        page.get_by_role("button", name="创建并进入项目").click()
                        expect(page.get_by_role("button", name="四步建岗向导")).to_be_visible()
                        with sqlite3.connect(workspace / "data" / "srw_v1.db") as db:
                            self.assertEqual(db.execute("SELECT COUNT(*) FROM project").fetchone()[0], 1)
                    finally:
                        browser.close()
            finally:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                os.close(master)

            self.assertFalse((workspace / "data" / "app.lock").exists(),
                             "graceful Local Web exit must release its workspace lease")


if __name__ == "__main__":
    unittest.main()
