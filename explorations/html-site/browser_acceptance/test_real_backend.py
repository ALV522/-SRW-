"""E1 browser + *real* SRW Starlette API + disposable SQLite acceptance.

Unlike the fast bridge fixture tests, this suite starts the real C11 Python API
and the separate E1 bridge, then drives Chromium against HTTP responses stored
in a temporary SQLite workspace. No user database, provider key or production
Knowledge database is accessed.

Requires playwright==1.56.0 and installed Chromium. Run only from the isolated
exploration workflow, never from the mainline test target.
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
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts" / "html-e1-browser"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request_json(base, path, payload=None, method=None):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        base + path,
        data=data,
        headers=headers,
        method=method or ("POST" if data is not None else "GET"),
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        body = response.read()
        if response.status != 200:
            raise AssertionError(f"unexpected status: {response.status}")
        return json.loads(body.decode("utf-8"))


def wait_ready(url, processes):
    for _ in range(120):
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f"synthetic service exited early with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=0.4) as r:
                if r.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError("synthetic service did not become ready")


class RealBackendE1Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(prefix="srw-html-e1-disposable-")
        cls.port_api = free_port()
        cls.port_web = free_port()
        cls.api = f"http://127.0.0.1:{cls.port_api}"
        cls.web = f"http://127.0.0.1:{cls.port_web}"
        cls.api_log = (EVIDENCE / "synthetic-srw-backend.log").open("w", encoding="utf-8")
        cls.bridge_log = (EVIDENCE / "synthetic-e1-bridge.log").open("w", encoding="utf-8")
        cls.backend = None
        cls.bridge = None
        cls.playwright = None
        cls.browser = None
        try:
            env = {**os.environ, "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1"}
            cls.backend = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "browser_acceptance" / "serve.py"),
                 "--workspace", cls.tmp.name, "--port", str(cls.port_api)],
                cwd=ROOT, env=env, stdout=cls.api_log, stderr=subprocess.STDOUT,
            )
            wait_ready(cls.api + "/health/ready", [cls.backend])

            cls.bridge = subprocess.Popen(
                [sys.executable, "-u", str(HERE / "serve_e1.py"),
                 "--upstream", cls.api, "--port", str(cls.port_web)],
                cwd=ROOT, env=env, stdout=cls.bridge_log, stderr=subprocess.STDOUT,
            )
            wait_ready(cls.web + "/", [cls.backend, cls.bridge])

            cls.project_name = "E1合成项目-" + uuid.uuid4().hex[:8]
            cls.candidate_name = "E1合成候选人-" + uuid.uuid4().hex[:8]
            cls.resume_text = "合成简历：负责跨部门招聘流程建设，具备结构化分析与候选人沟通经验。"
            project = request_json(cls.api, "/api/v1/projects", {
                "title": cls.project_name,
                "role_title": "模拟招聘分析师",
                "brief_summary": "一次性数据，仅用于隔离 E1 浏览器验收",
            })
            cls.pid = project["project_id"]
            candidate = request_json(cls.api, f"/api/v1/projects/{cls.pid}/candidates", {
                "display_name": cls.candidate_name,
            })
            cls.cid = candidate["candidate_id"]
            material = request_json(cls.api, f"/api/v1/candidates/{cls.cid}/sources/text", {
                "text_content": cls.resume_text,
                "filename": "e1-synthetic-resume.txt",
                "source_kind": "resume",
                "publish_material": True,
            })
            cls.sid = material["source_id"]
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except BaseException:
            cls.cleanup()
            raise

    @classmethod
    def cleanup(cls):
        if cls.browser:
            cls.browser.close()
            cls.browser = None
        if cls.playwright:
            cls.playwright.stop()
            cls.playwright = None
        for name in ("bridge", "backend"):
            process = getattr(cls, name, None)
            if process:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for name in ("bridge_log", "api_log"):
            obj = getattr(cls, name, None)
            if obj:
                obj.close()
        if getattr(cls, "tmp", None):
            cls.tmp.cleanup()
            cls.tmp = None

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(
            locale="zh-CN",
            viewport={"width": 1440, "height": 900},
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)
        self.errors = []
        self.requests = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda req: self.requests.append((req.method, req.url)))

    def tearDown(self):
        outcome = getattr(self, "_outcome", None)
        result = getattr(outcome, "result", None) if outcome else None
        errors = []
        if result is not None:
            errors = [x for x in (result.errors + result.failures) if x[0] is self]
        if errors:
            try:
                self.page.screenshot(
                    path=str(EVIDENCE / (self._testMethodName + ".png")),
                    full_page=True,
                )
            except Exception:
                pass
        self.context.close()

    def open_live(self):
        self.page.goto(self.web + "/", wait_until="domcontentloaded")
        expect(self.page.locator("#api-state")).to_have_text("LIVE · web · GET-only")
        self.assertFalse(self.errors, self.errors)

    def open_candidate(self):
        self.page.locator("[data-page=projects]").click()
        expect(self.page.locator("#root")).to_contain_text(self.project_name)
        self.page.get_by_role("button", name="打开项目").click()
        expect(self.page.locator("#root h1")).to_have_text(self.project_name)
        self.page.get_by_role("button", name="打开工作空间").click()
        expect(self.page.locator(".candidate-side h1")).to_have_text(self.candidate_name)

    def test_01_real_service_identity_and_navigation(self):
        self.open_live()
        self.assertEqual(request_json(self.web, "/api/v1/info")["product"], "SRW")
        self.assertEqual(request_json(self.web, "/api/v1/runtime/info")["edition"], "web")
        expect(self.page.locator("#root")).to_contain_text("当前是")
        self.open_candidate()
        expect(self.page.locator(".source")).to_contain_text(self.resume_text)
        expect(self.page.locator(".source")).to_contain_text("e1-synthetic-resume.txt")
        expect(self.page.locator(".candidate-side")).to_contain_text("简历筛选")
        self.assertEqual(request_json(self.web,
            f"/api/v1/candidates/{self.cid}/workspace")["sources"][0]["source_id"], self.sid)
        self.assertFalse(self.errors, self.errors)
        self.assertTrue(all(method == "GET" for method, _ in self.requests), self.requests)

    def test_02_backend_update_visible_after_browser_refresh(self):
        self.open_live()
        self.open_candidate()
        expect(self.page.locator(".candidate-side")).to_contain_text("简历筛选")
        # Writes go straight to the disposable true backend, simulating another
        # carrier; E1 Web is deliberately forbidden to write.
        changed = request_json(self.api, f"/api/v1/candidates/{self.cid}/stage", {
            "stage": "shortlisted",
            "actor": "human",
            "reason": "synthetic second-carrier update",
        })
        self.assertEqual(changed["pipeline_stage"], "shortlisted")
        self.page.reload()
        expect(self.page.locator("#api-state")).to_have_text("LIVE · web · GET-only")
        self.open_candidate()
        expect(self.page.locator(".candidate-side")).to_contain_text("短名单")
        self.assertFalse(self.errors, self.errors)
        self.assertTrue(all(method == "GET" for method, _ in self.requests), self.requests)

    def test_03_bridge_denies_mutations_and_sensitive_get(self):
        self.open_live()
        before = request_json(self.api, "/api/v1/projects")["projects"]
        response = self.context.request.post(
            self.web + "/api/v1/projects",
            data={"title": "MUST_NOT_BE_CREATED", "role_title": "blocked"},
        )
        self.assertEqual(response.status, 405)
        denied = self.context.request.get(
            self.web + f"/api/v1/sources/{self.sid}/file",
        )
        self.assertEqual(denied.status, 404)
        after = request_json(self.api, "/api/v1/projects")["projects"]
        self.assertEqual(len(before), len(after))
        self.assertFalse(any(x.get("title") == "MUST_NOT_BE_CREATED" for x in after))
        self.assertFalse(self.errors, self.errors)

    def test_04_browser_and_core_share_one_data_identity(self):
        self.open_live()
        browser_info = self.page.evaluate("state.serviceInfo")
        core_info = request_json(self.api, "/api/v1/info")
        self.assertEqual(browser_info["instance_id"], core_info["instance_id"])
        self.assertEqual(browser_info["data_dir_identity"], core_info["data_dir_identity"])
        self.assertEqual(self.page.evaluate("state.mode"), "live")
        self.assertFalse(self.errors, self.errors)


if __name__ == "__main__":
    unittest.main()
