"""Real-browser acceptance for cancelling a scheduled restore across a restart.

The gap this closes: until now a cancelled restore was only proven at the marker
level (`POST /system/restore/cancel` returns ``scheduled=false``, diagnostics says
false). Nothing proved the operator-visible consequence - "I cancelled, I restarted,
and the work I did after scheduling a backup is still here". The opposite path
(schedule, restart, restore happens) is proven by
``convergence_tests/test_real_restore_restart.py``, but that is a source/API test
with no browser and it asserts data survival only.

So this module runs two complementary scenarios against a real Core and a real
Chromium page:

* positive: create project A, back up, schedule a restore **through the UI**,
  create project B plus a candidate and a text source afterwards, cancel the
  schedule **through the UI banner**, shut the Core down gracefully (lease must be
  released), restart the same workspace, and verify B, its candidate, its Source
  and its audit events all survived;
* negative control: the same flow **without** cancelling. The restart must really
  overwrite - B and its work must be gone and only A must remain. Without this
  control the positive test would pass even if "cancel" did nothing, so the pair
  is the actual proof.

Level: real process + real HTTP + real Chromium + real SQLite/blobs. Not WPF GUI,
not embedded Python, not production Knowledge. Synthetic data only.
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
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
# The Chromium job runs with PYTHONPATH=backend only, so the shared synthetic
# Knowledge fixture that lives beside the source tests is not importable by
# default. Adding its directory keeps one fixture definition instead of copying
# a 94-line generator into the browser suite.
if str(ROOT / "convergence_tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "convergence_tests"))

from knowledge_fixture import create_minimal_knowledge_tree  # noqa: E402
from srw.workspace_lease import ABSENT, inspect_lease  # noqa: E402


def free_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RestoreCancelRestartAcceptance(unittest.TestCase):
    """Each test owns its workspace, port and Core process lifecycle."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-cancel-restart-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")
        self.port = free_loopback_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = dict(os.environ)
        self.env.update({
            "RECRUITMENT_DATA_DIR": str(self.data),
            "RECRUITMENT_FRONTEND_DIST": str(ROOT / "frontend" / "dist"),
            "RECRUITMENT_KNOWLEDGE_DIR": str(knowledge),
            "PYTHONPATH": os.pathsep.join((str(ROOT / "backend"), str(ROOT / "scripts"))),
        })
        self.processes: list[subprocess.Popen] = []
        self.addCleanup(self.stop_any_processes)
        self.stderr = (self.root / "backend.stderr.log").open("w+b")
        self.addCleanup(self.stderr.close)

        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page_errors: list[str] = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))

    # ---------------------------------------------------------------- processes

    def stop_any_processes(self) -> None:
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)

    def make_process(self) -> subprocess.Popen:
        proc = subprocess.Popen(
            [sys.executable, "-B", str(ROOT / "scripts" / "run_local.py"),
             "--host", "127.0.0.1", "--port", str(self.port),
             "--edition", "web", "--workspace-lock", "backend"],
            cwd=ROOT, env=self.env, stdout=subprocess.DEVNULL, stderr=self.stderr,
        )
        self.processes.append(proc)
        return proc

    def start_core(self) -> subprocess.Popen:
        proc = self.make_process()
        for _ in range(200):
            if proc.poll() is not None:
                self.fail(f"Core exited before readiness, returncode={proc.returncode}")
            try:
                with urllib.request.urlopen(self.base + "/health/ready", timeout=0.4) as ready:
                    if ready.status == 200:
                        return proc
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        self.fail("Core did not become ready inside the bounded startup window")

    def stop_core(self, proc: subprocess.Popen) -> None:
        """Graceful shutdown, then prove the workspace lease was released.

        A surviving lease would make the restarted Core refuse to start, which
        would turn this test into a false failure - so it is asserted explicitly.
        """
        self.api("POST", "/api/v1/runtime/shutdown", {})
        self.assertEqual(proc.wait(timeout=25), 0)
        self.assertEqual(inspect_lease(self.data).state, ABSENT)

    # ------------------------------------------------------------------- http

    def api(self, method: str, path: str, payload: dict | None = None):
        raw = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=raw, method=method,
            headers={"Content-Type": "application/json"} if payload is not None else {},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            # Read once, then assert: passing response.read() as the assertion
            # message would consume the body first and leave nothing to parse.
            body = response.read()
            expected = 202 if path == "/api/v1/runtime/shutdown" else 200
            self.assertEqual(response.status, expected, body[:400])
        return json.loads(body) if body else {}

    def status_of(self, path: str) -> int:
        """Return the HTTP status for a read, including error codes."""
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def projects(self) -> dict[str, str]:
        return {row["project_id"]: row["title"]
                for row in self.api("GET", "/api/v1/projects")["projects"]}

    def project_id_by_title(self, title: str) -> str:
        for project_id, name in self.projects().items():
            if name == title:
                return project_id
        self.fail(f"project {title!r} is not listed")

    # -------------------------------------------------------------------- ui

    def open_ui(self) -> None:
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        expect(self.page.locator("#content h1")).to_be_visible()

    def create_project_via_ui(self, title: str) -> None:
        self.page.locator("aside .nav-item", has_text="工作台总览").click()
        expect(self.page.locator("#content h1")).to_have_text("工作台总览")
        self.page.get_by_role("button", name="＋ 新建招聘项目").click()
        self.page.locator("#np-title").fill(title)
        self.page.locator("#np-role").fill("Synthetic recovery analyst")
        self.page.get_by_role("button", name="创建并进入项目").click()
        expect(self.page.locator("#top-title")).to_have_text("招聘项目")
        expect(self.page.locator("#content .project-banner h2")).to_have_text(title)

    def schedule_restore_via_ui(self, filename: str) -> str:
        """Click the operator's schedule button and return the confirmation text.

        The dialog text is returned rather than discarded so the test proves the
        schedule confirmation itself warns about post-schedule data loss; a future
        edit that drops that warning fails here.
        """
        self.page.locator("aside .nav-item", has_text="系统设置").click()
        expect(self.page.locator("#top-title")).to_have_text("系统设置")
        expect(self.page.locator("#content")).to_contain_text(filename)
        seen: dict[str, str] = {}

        def accept(dialog) -> None:
            seen["message"] = dialog.message
            dialog.accept()

        self.page.once("dialog", accept)
        self.page.get_by_role("button", name="下次启动恢复").first.click()
        expect(self.page.locator("#restore-banner")).to_be_visible()
        return seen.get("message", "")

    def cancel_schedule_via_ui(self) -> None:
        expect(self.page.locator("#restore-banner")).to_be_visible()
        self.page.once("dialog", lambda dialog: dialog.accept())
        self.page.get_by_role("button", name="取消待恢复计划").click()
        expect(self.page.locator("#restore-banner")).to_have_count(0)

    # ------------------------------------------------------------- work to keep

    def add_audited_work(self, project_id: str, name: str) -> tuple[str, str, str]:
        """Create a candidate and a published text Source.

        Both write audit events (CANDIDATE_CREATED, SOURCE_ADDED), but an audit row
        can outlive the row it describes, so the returned ``source_id`` is what lets
        the caller read the payload back after the restart. Project creation itself
        writes no audit row (verified against a running Core), which is why the
        candidate/source pair carries the evidence.
        """
        candidate = self.api("POST", f"/api/v1/projects/{project_id}/candidates",
                             {"display_name": name})
        candidate_id = candidate["candidate_id"]
        text = "Synthetic evidence written after scheduling."
        created = self.api("POST", f"/api/v1/candidates/{candidate_id}/sources/text",
                           {"text_content": text, "publish_material": True})
        return candidate_id, created["source_id"], text

    # ------------------------------------------------------------------ tests

    def test_cancelled_restore_keeps_later_work_across_restart(self) -> None:
        core = self.start_core()
        self.open_ui()
        kept_title = "synthetic pre-schedule project"
        self.create_project_via_ui(kept_title)
        kept_id = self.project_id_by_title(kept_title)

        filename = self.api("POST", "/api/v1/system/backups", {})["filename"]
        dialog = self.schedule_restore_via_ui(filename)
        self.assertIn("可能全部丢失", dialog,
                      "the schedule confirmation must warn about post-schedule loss")

        # Everything below happens *after* the restore was scheduled, so it is
        # exactly the work a restart would destroy.
        later_title = "synthetic post-schedule project"
        self.create_project_via_ui(later_title)
        expect(self.page.locator("#restore-banner")).to_be_visible()
        later_id = self.project_id_by_title(later_title)
        candidate_id, source_id, source_text = self.add_audited_work(
            later_id, "Synthetic later candidate")

        self.cancel_schedule_via_ui()
        self.assertFalse(self.api("GET", "/api/v1/system/diagnostics")["pending_restore"],
                         "cancel must clear the marker before the restart")
        self.stop_core(core)
        self.assertFalse((self.data / "pending_restore.json").exists())

        restarted = self.start_core()
        try:
            titles = self.projects()
            self.assertIn(later_id, titles, "the post-schedule project must survive a cancelled restore")
            self.assertEqual(titles[later_id], later_title)
            self.assertEqual(titles[kept_id], kept_title)
            self.assertFalse(self.api("GET", "/api/v1/system/diagnostics")["pending_restore"])

            candidates = self.api("GET", f"/api/v1/projects/{later_id}/candidates")["candidates"]
            self.assertIn(candidate_id, {row["candidate_id"] for row in candidates})
            audit = self.api("GET", f"/api/v1/projects/{later_id}/audit")["audit_events"]
            event_types = [row["event_type"] for row in audit]
            self.assertIn("CANDIDATE_CREATED", event_types)
            self.assertIn("SOURCE_ADDED", event_types)

            # An audit row can outlive the row it describes, so read the Source
            # payload itself. This is the assertion the PR previously lacked.
            content = self.api("GET", f"/api/v1/sources/{source_id}/content")
            self.assertEqual(content["candidate_id"], candidate_id)
            self.assertTrue(content["has_text"], "reinstated Source must still carry text")
            self.assertEqual(content["text_content"], source_text,
                             "the original synthetic text must survive byte for byte")

            # Operator-visible proof, not just API state: reopen the UI and read
            # both projects off the rendered project list.
            self.open_ui()
            self.page.locator("aside .nav-item", has_text="招聘项目").click()
            expect(self.page.locator("#content")).to_contain_text(later_title)
            expect(self.page.locator("#content")).to_contain_text(kept_title)
            self.assertEqual(self.page_errors, [], self.page_errors)
        finally:
            self.stop_core(restarted)

    def test_uncaught_schedule_restart_really_overwrites_later_work(self) -> None:
        """Negative control: without cancel the same flow must lose project B.

        This is what gives the positive case meaning. It also proves the restart
        actually applied the restore instead of silently skipping it.
        """
        core = self.start_core()
        self.open_ui()
        kept_title = "synthetic retained project"
        self.create_project_via_ui(kept_title)
        kept_id = self.project_id_by_title(kept_title)

        filename = self.api("POST", "/api/v1/system/backups", {})["filename"]
        self.schedule_restore_via_ui(filename)

        later_title = "synthetic discarded project"
        self.create_project_via_ui(later_title)
        later_id = self.project_id_by_title(later_title)
        _, discarded_source_id, _ = self.add_audited_work(
            later_id, "Synthetic discarded candidate")
        self.assertTrue((self.data / "pending_restore.json").is_file())

        self.stop_core(core)
        restarted = self.start_core()
        try:
            titles = self.projects()
            self.assertIn(kept_id, titles)
            self.assertNotIn(later_id, titles,
                             "an uncancelled restore must overwrite the later project")
            self.assertEqual(self.status_of(f"/api/v1/sources/{discarded_source_id}/content"), 404,
                             "the discarded Source payload must not survive the restore")
            self.assertFalse((self.data / "pending_restore.json").exists())
            snapshots = list((self.data / "backups").glob("pre_restore-*.zip"))
            self.assertEqual(len(snapshots), 1, "the restore must leave one pre-restore snapshot")
        finally:
            self.stop_core(restarted)


if __name__ == "__main__":
    unittest.main()
