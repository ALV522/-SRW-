"""Isolated synthetic E1 security and interoperability checks.

No production SRW database, user data, provider credentials or EXE is used.
Run: python -m unittest discover -s explorations/html-site -p 'test_e1*.py' -v
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("srw_e1_bridge", HERE / "serve_e1.py")
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class FakeSRWHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    version = "1.0.0-alpha10-convergence11"
    instance = "e1-synthetic-instance"
    session = "e1-synthetic-session"
    data_hash = "synthetic-data-scope-hash"
    product = "SRW"
    redirect_projects = False
    forwarded_gets = []
    forwarded_mutations = []

    def log_message(self, *_args):
        pass

    def do_GET(self):
        type(self).forwarded_gets.append(self.path)
        if self.path == "/api/v1/projects" and self.redirect_projects:
            self.send_response(302)
            self.send_header("Location", "https://example.com/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/api/v1/info":
            data = {
                "product": self.product,
                "version": self.version,
                "instance_id": self.instance,
                "data_dir_identity": self.data_hash,
            }
        elif self.path == "/api/v1/runtime/info":
            data = {
                "product": self.product,
                "version": self.version,
                "instanceId": self.instance,
                "sessionId": self.session,
                "runtime": "desktop",
                "edition": "windows",
                "dataScopeId": self.data_hash,
            }
        elif self.path == "/health/ready":
            data = {"status": "ready", "schema_revision": "v1_0014"}
        elif self.path == "/api/v1/dashboard":
            data = {"metrics": {"candidates": 3}}
        elif self.path == "/api/v1/projects":
            data = {"projects": [{"project_id": "p1", "title": "Synthetic Project"}]}
        elif self.path.startswith("/api/v1/projects/p1/candidates"):
            data = {"candidates": [{"candidate_id": "c1", "display_name": "Synthetic Candidate"}]}
        elif self.path == "/api/v1/projects/p1/pipeline":
            data = {"stages": {"screening": 1}}
        elif self.path == "/api/v1/candidates/c1/summary":
            data = {"candidate_id": "c1", "project_id": "p1", "display_name": "Synthetic Candidate"}
        elif self.path == "/api/v1/candidates/c1/workspace":
            data = {"candidate_id": "c1", "claims": [], "criteria": [], "sources": []}
        elif self.path == "/api/v1/candidates/c1/brief":
            data = {"candidate_id": "c1", "action_plan": {}}
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        type(self).forwarded_mutations.append(self.path)
        self.send_response(500)
        self.send_header("Content-Length", "0")
        self.end_headers()


class E1BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeSRWHandler)
        cls.upstream_port = cls.upstream.server_address[1]
        cls.upstream_url = f"http://127.0.0.1:{cls.upstream_port}"
        cls.upstream_thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.upstream_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.upstream_thread.join(timeout=5)

    def setUp(self):
        FakeSRWHandler.forwarded_gets = []
        FakeSRWHandler.forwarded_mutations = []
        FakeSRWHandler.redirect_projects = False
        FakeSRWHandler.product = "SRW"

        bridge.ReadOnlyBridge.upstream = self.upstream_url
        self.viewer = ThreadingHTTPServer(("127.0.0.1", 0), bridge.ReadOnlyBridge)
        bridge.ReadOnlyBridge.listen_port = self.viewer.server_address[1]
        self.viewer_url = f"http://127.0.0.1:{bridge.ReadOnlyBridge.listen_port}"
        self.viewer_thread = threading.Thread(target=self.viewer.serve_forever, daemon=True)
        self.viewer_thread.start()

    def tearDown(self):
        self.viewer.shutdown()
        self.viewer.server_close()
        self.viewer_thread.join(timeout=5)

    def get(self, path, headers=None, method="GET"):
        req = Request(self.viewer_url + path, method=method, headers=headers or {})
        try:
            with urlopen(req, timeout=5) as r:
                return r.status, r.read(), r.headers
        except HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def test_read_only_frontend_and_dashboard(self):
        status, html, _ = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"SRW E1", html)
        status, payload, headers = self.get("/api/v1/dashboard")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["metrics"]["candidates"], 3)
        self.assertEqual(headers["X-SRW-Exploration"], "html-e1-read-only")

    def test_core_project_candidate_reads(self):
        paths = (
            "/api/v1/projects",
            "/api/v1/projects/p1/pipeline",
            "/api/v1/projects/p1/candidates?archived=active&limit=100",
            "/api/v1/candidates/c1/summary",
            "/api/v1/candidates/c1/workspace",
            "/api/v1/candidates/c1/brief",
        )
        for path in paths:
            with self.subTest(path=path):
                status, payload, _ = self.get(path)
                self.assertEqual(status, 200, payload)

    def test_no_mutation_reaches_upstream(self):
        for method in ("POST", "PATCH", "PUT", "DELETE", "OPTIONS"):
            with self.subTest(method=method):
                status, _, _ = self.get("/api/v1/projects", method=method)
                self.assertEqual(status, 405)
        self.assertEqual(FakeSRWHandler.forwarded_mutations, [])

    def test_unlisted_get_routes_are_not_proxied(self):
        for path in (
            "/api/v1/system/backups",
            "/api/v1/sources/s1/file",
            "/api/v1/settings/providers",
            "/api/v1/unknown",
            "/unexpected",
        ):
            with self.subTest(path=path):
                status, _, _ = self.get(path)
                self.assertEqual(status, 404)
        self.assertEqual(FakeSRWHandler.forwarded_gets, [])

    def test_rejects_foreign_host_and_origin(self):
        self.assertEqual(self.get("/", headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.get("/api/v1/dashboard", headers={"Origin": "https://attacker.example"})[0], 403)
        self.assertEqual(self.get("/api/v1/dashboard", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(FakeSRWHandler.forwarded_gets, [])

    def test_does_not_follow_upstream_redirects(self):
        FakeSRWHandler.redirect_projects = True
        status, body, _ = self.get("/api/v1/projects")
        self.assertEqual(status, 502)
        self.assertIn(b"redirect blocked", body)

    def test_explicit_loopback_upstream_probe(self):
        target, runtime = bridge.select_upstream(
            supplied_url=self.upstream_url,
            data_root=None,
        )
        self.assertEqual(target, self.upstream_url)
        self.assertEqual(runtime["instanceId"], FakeSRWHandler.instance)

    def test_rejects_invalid_upstream_origins(self):
        for value in (
            "http://example.com:8000",
            "https://127.0.0.1:8000",
            "http://127.0.0.1:8000/api",
            "http://user:pass@127.0.0.1:8000",
            "http://127.0.0.1",
        ):
            with self.subTest(url=value):
                with self.assertRaises(ValueError):
                    bridge.require_loopback_upstream(value)

    def test_lease_identity_and_dynamic_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "app.lock"
            folder.mkdir()
            lease_path = folder / "instance.json"
            metadata = {
                "edition": "windows",
                "port": self.upstream_port,
                "instance_id": FakeSRWHandler.instance,
                "session_id": FakeSRWHandler.session,
                "version": FakeSRWHandler.version,
                "data_root_hash": FakeSRWHandler.data_hash,
            }
            lease_path.write_text(json.dumps(metadata), encoding="utf-8")
            selected, runtime = bridge.select_upstream(supplied_url=None, data_root=tmp)
            self.assertEqual(selected, self.upstream_url)
            self.assertEqual(runtime["edition"], "windows")

            metadata["session_id"] = "wrong-session"
            lease_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                bridge.select_upstream(supplied_url=None, data_root=tmp)

    def test_rejects_non_srw_service(self):
        FakeSRWHandler.product = "OtherApp"
        with self.assertRaisesRegex(ValueError, "not SRW"):
            bridge.select_upstream(supplied_url=self.upstream_url, data_root=None)


if __name__ == "__main__":
    unittest.main()
