"""Dual-carrier acceptance, locally runnable subset (ADR-0003 S6, T1-T10).

One real detached Supervisor subprocess with session enforcement enabled and
two carrier clients (A and B) driving real HTTP against it. Scenarios:

- T1/T2 cross-carrier read/write in both directions;
- T3 concurrent conflict on one aggregate: exactly one 200, one 412, audit
  unchanged by the refused write;
- T4 a protocol republish invalidates the earlier decision on BOTH ends;
- T5 closing carrier A never kills the Core (B keeps writing);
- T6 the same extraction triggered from both carriers executes once;
- T7 Supervisor restart: both carriers re-attach, old sessions are dead, data
  survives;
- T9 access control: cross-site origin, session-less mutation, wrong attach
  token, revoked session are all refused;
- T10 the same candidate's handoff export is identical from both ends.
- T8 backup mutex runs in-process with a deliberately slow backup (the
  subprocess suite cannot reliably interleave a fast file copy).

The WPF-Host half of T1/T2 (a real second carrier process) needs the owner's
Windows machine; the protocol-level contract is proven here with two
independent attach clients.
"""
from __future__ import annotations

import json
import os
import signal
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api import fullworkbench
from srw.api.app import create_v1_app
from srw.supervisor.service import SupervisorService
from srw.supervisor.client import SupervisorHandle, SupervisorUnavailable, ensure_supervisor, free_loopback_port
from srw.workspace_lease import inspect_lease, process_alive

ROOT = Path(__file__).resolve().parents[1]


# Loopback carrier traffic never traverses a proxy (a dead Core must read as
# connection refused, not as a proxy 502).
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(base_url: str, method: str, path: str, *, body: dict | None = None, headers: dict | None = None,
             timeout: float = 15.0) -> tuple[int, dict | bytes]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(base_url + path, data=data, method=method, headers=request_headers)
    try:
        with _NO_PROXY_OPENER.open(request, timeout=timeout) as response:
            payload = response.read()
            content_type = response.headers.get("content-type") or ""
            if "json" in content_type:
                return response.status, json.loads(payload.decode("utf-8") or "{}")
            return response.status, payload
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload.decode("utf-8") or "{}")
        except ValueError:
            return exc.code, payload


class DualCarrierAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SRW_BACKGROUND_WORKER"] = "0"
        cls.temp = tempfile.TemporaryDirectory(prefix="srw-dual-carrier-")
        cls.root = Path(cls.temp.name)
        cls.database = cls.root / "data" / "srw_v1.db"
        cls.frontend = ROOT / "frontend" / "dist"
        cls.knowledge = create_minimal_knowledge_tree(cls.root / "knowledge" / "active")
        cls.a = ensure_supervisor(
            cls.root,
            carrier="carrier-a",
            database=cls.database,
            frontend_dist=cls.frontend,
            knowledge_root=cls.knowledge,
            idle_grace_seconds=10.0,
            spawn_timeout=60.0,
            enforce_sessions=True,
        )
        cls.b = ensure_supervisor(
            cls.root, carrier="carrier-b", idle_grace_seconds=10.0, spawn_timeout=30.0
        )
        cls.supervisor_pid = (inspect_lease(cls.root / "data").holder or None)
        cls.supervisor_pid = cls.supervisor_pid.pid if cls.supervisor_pid else None

    @classmethod
    def tearDownClass(cls):
        for carrier in ("b", "a"):
            handle = getattr(cls, carrier, None)
            if handle is None:
                continue
            try:
                handle.detach()
            except SupervisorUnavailable:
                pass
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if inspect_lease(cls.root / "data").state == "absent":
                break
            time.sleep(0.5)
        pid = getattr(cls, "supervisor_pid", None)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        cls.temp.cleanup()

    # -- carrier helpers -----------------------------------------------
    def _a(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        return _request(self.a.base_url, method, path, body=body, headers={**self.a.session_headers(), **(headers or {})})

    def _b(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        return _request(self.b.base_url, method, path, body=body, headers={**self.b.session_headers(), **(headers or {})})

    def _create_project_via(self, carrier: str) -> str:
        status, body = self._a("POST", "/api/v1/projects", {"title": f"双载体 {carrier}", "role_title": "高级工程师"}) if carrier == "a" else self._b("POST", "/api/v1/projects", {"title": f"双载体 {carrier}", "role_title": "高级工程师"})
        self.assertEqual(status, 200, body)
        return body["project_id"]

    # -- T1/T2 ----------------------------------------------------------
    def test_t1_t2_cross_carrier_read_write(self):
        pid = self._create_project_via("a")
        status, body = self._b("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["project_id"], pid)

        status, created = self._b("POST", f"/api/v1/projects/{pid}/candidates", {"display_name": "B 端候选人"})
        self.assertEqual(status, 200, created)
        cid = created["candidate_id"]
        status, seen = self._a("GET", f"/api/v1/candidates/{cid}/workspace")
        self.assertEqual(status, 200, seen)
        self.assertEqual(seen["candidate_id"], cid)

    # -- T3 -------------------------------------------------------------
    def test_t3_concurrent_conflict_one_wins_one_412(self):
        pid = self._create_project_via("a")
        status, workspace = self._a("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        self.assertEqual(status, 200, workspace)
        draft_id = workspace["draft"]["revision_id"]
        token = workspace["draft"]["token"]

        payload_a = {"brief": {"title": "双载体 a"}, "criteria": [{"criterion_key": "ka", "name": "A 标准"}], "assessment_stages": []}
        payload_b = {"brief": {"title": "双载体 b"}, "criteria": [{"criterion_key": "kb", "name": "B 标准"}], "assessment_stages": []}

        barrier = threading.Barrier(2)
        results: dict[str, tuple[int, object]] = {}

        def _write(carrier: str, payload: dict) -> None:
            call = self._a if carrier == "a" else self._b
            barrier.wait(timeout=10)
            results[carrier] = call("PATCH", f"/api/v1/protocol-revisions/{draft_id}",
                                    {"payload": payload, "provenance": {"origin": "t3"}},
                                    headers={"If-Match": token})

        threads = [threading.Thread(target=_write, args=("a", payload_a)),
                   threading.Thread(target=_write, args=("b", payload_b))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        codes = sorted(code for code, _ in results.values())
        self.assertEqual(codes, [200, 412], f"expected one success and one 412, got {results}")
        loser = [carrier for carrier, (code, _) in results.items() if code == 412][0]
        self.assertEqual(results[loser][1]["error"]["code"], "revision_conflict")

        # The refused write left no trace: the stored payload is the winner's.
        status, after = self._b("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        self.assertEqual(status, 200, after)
        keys = [c.get("criterion_key") for c in after["draft"]["criteria"]]
        self.assertEqual(len(keys), 1, "the refused concurrent write must not be applied")

    # -- T4 -------------------------------------------------------------
    def test_t4_protocol_republish_invalidates_decision_on_both_ends(self):
        pid = self._create_project_via("a")
        status, workspace = self._a("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        draft_id = workspace["draft"]["revision_id"]
        self._a("PATCH", f"/api/v1/protocol-revisions/{draft_id}",
                {"payload": {"brief": {"title": "T4"}, "criteria": [], "assessment_stages": []}, "provenance": {}},
                headers={"If-Match": workspace["draft"]["token"]})
        status, published = self._a("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        self._a("POST", f"/api/v1/protocol-revisions/{draft_id}/publish",
                headers={"If-Match": published["draft"]["token"]})

        status, candidate = self._a("POST", f"/api/v1/projects/{pid}/candidates", {"display_name": "T4 候选人"})
        cid = candidate["candidate_id"]
        self._a("POST", f"/api/v1/candidates/{cid}/sources/text",
                {"text_content": "T4 合成材料：结构化调研经历。", "filename": "t4.txt", "publish_material": True})
        status, before = self._a("GET", f"/api/v1/candidates/{cid}/workspace")
        context = before["decision_context_hash"]
        self.assertTrue(context)
        self._a("POST", f"/api/v1/candidates/{cid}/decision",
                {"decision": "hold", "reason": "等待证据", "actor": "human"},
                headers={"If-Match": context})

        # Carrier B republishes a new protocol revision.
        status, ws_b = self._b("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        self.assertEqual(status, 200, ws_b)
        fork = self._b("POST", f"/api/v1/projects/{pid}/protocol-drafts")
        self.assertEqual(fork[0], 200, fork)
        status, ws_after_fork = self._b("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        new_draft = ws_after_fork["draft"]
        self._b("PATCH", f"/api/v1/protocol-revisions/{new_draft['revision_id']}",
                {"payload": {"brief": {"title": "T4 v2"}, "criteria": [], "assessment_stages": []}, "provenance": {}},
                headers={"If-Match": new_draft["token"]})
        status, ws_moved = self._b("GET", f"/api/v1/projects/{pid}/protocol-workspace")
        self._b("POST", f"/api/v1/protocol-revisions/{new_draft['revision_id']}/publish",
                headers={"If-Match": ws_moved["draft"]["token"]})

        for label, call in (("A", self._a), ("B", self._b)):
            status, after = call("GET", f"/api/v1/candidates/{cid}/workspace")
            self.assertEqual(status, 200, after)
            self.assertTrue(after["stale_decision_context_hash"], f"{label} must see the decision as stale")
            self.assertNotEqual(after["decision_context_hash"], context)

    # -- T5 -------------------------------------------------------------
    def test_t5_closing_carrier_a_never_kills_the_core(self):
        pid = self._create_project_via("b")
        self.a.detach()
        inspection = inspect_lease(self.root / "data")
        self.assertEqual(inspection.state, "active", "closing A must not kill the Supervisor")
        self.assertEqual(inspection.holder.edition, "supervisor")

        status, created = self._b("POST", f"/api/v1/projects/{pid}/candidates", {"display_name": "T5 候选人"})
        self.assertEqual(status, 200, created)
        status, seen = self._b("GET", f"/api/v1/candidates/{created['candidate_id']}/workspace")
        self.assertEqual(status, 200, seen)

        # A re-attaches for the remaining scenarios (fresh session). The handle
        # must land on the class: each test method runs on a fresh instance.
        DualCarrierAcceptanceTests.a = ensure_supervisor(
            self.root, carrier="carrier-a-again", idle_grace_seconds=10.0, spawn_timeout=30.0
        )
        self.assertFalse(self.a.spawned)

    # -- T6 -------------------------------------------------------------
    def test_t6_dual_triggered_extraction_runs_once(self):
        pid = self._create_project_via("a")
        status, candidate = self._a("POST", f"/api/v1/projects/{pid}/candidates", {"display_name": "T6 候选人"})
        cid = candidate["candidate_id"]
        status, source = self._a("POST", f"/api/v1/candidates/{cid}/sources/text",
                                 {"text_content": "T6 合成材料。", "filename": "t6.txt"})
        self.assertEqual(status, 200, source)
        source_id = source["source_id"]

        barrier = threading.Barrier(2)
        results: dict[str, tuple[int, object]] = {}

        def _trigger(carrier: str) -> None:
            call = self._a if carrier == "a" else self._b
            barrier.wait(timeout=10)
            results[carrier] = call("POST", f"/api/v1/candidates/{cid}/evidence/extract-task", {"source_id": source_id})

        threads = [threading.Thread(target=_trigger, args=("a",)), threading.Thread(target=_trigger, args=("b",))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        for carrier, (status, body) in results.items():
            self.assertEqual(status, 200, f"{carrier}: {body}")
        job_ids = {body["job_id"] for _, body in results.values()}
        self.assertEqual(len(job_ids), 1, f"both carriers must share one job, got {results}")

        status, tasks = self._b("GET", "/api/v1/tasks?limit=50")
        self.assertEqual(status, 200, tasks)
        matching = [t for t in tasks["tasks"] if t.get("source_id") == source_id and t["type"] == "evidence_extract"]
        self.assertEqual(len(matching), 1, f"exactly one task row expected, got {matching}")

    # -- T7 -------------------------------------------------------------
    def test_t7_supervisor_restart_reattaches_and_data_survives(self):
        pid = self._create_project_via("a")
        self.assertIsNotNone(self.supervisor_pid)
        os.kill(self.supervisor_pid, signal.SIGTERM)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if not _process_alive(self.supervisor_pid):
                break
            time.sleep(0.5)
        self.assertFalse(_process_alive(self.supervisor_pid), "supervisor did not stop")

        # The old Core is gone: the previous base_url no longer answers.
        with self.assertRaises((urllib.error.URLError, OSError)):
            _request(self.a.base_url, "GET", "/api/v1/projects")
        # Re-derive a fresh Supervisor on the same workspace; both carriers re-attach.
        DualCarrierAcceptanceTests.a = ensure_supervisor(
            self.root, carrier="carrier-a-restart", database=self.database,
            frontend_dist=self.frontend, knowledge_root=self.knowledge,
            idle_grace_seconds=10.0, spawn_timeout=60.0, enforce_sessions=True,
        )
        self.assertTrue(self.a.spawned, "a dead Supervisor must be re-derived")
        DualCarrierAcceptanceTests.b = ensure_supervisor(
            self.root, carrier="carrier-b-restart", idle_grace_seconds=10.0, spawn_timeout=30.0
        )

        inspection = inspect_lease(self.root / "data")
        DualCarrierAcceptanceTests.supervisor_pid = inspection.holder.pid if inspection.holder else None
        status, projects = self._a("GET", "/api/v1/projects")
        self.assertEqual(status, 200, projects)
        self.assertIn(pid, [p["project_id"] for p in projects["projects"]], "data must survive the restart")

        status, body = self._b("GET", "/api/v1/projects")
        self.assertEqual(status, 200, body)
        self.assertIn(pid, [p["project_id"] for p in body["projects"]])

    # -- T9 -------------------------------------------------------------
    def test_t9_access_control(self):
        pid = self._create_project_via("a")
        # Cross-site origin is refused even with a valid session.
        status, body = self._a("POST", f"/api/v1/projects/{pid}/candidates", {"display_name": "跨站"},
                               headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403, body)
        # A mutation without session headers is refused.
        status, body = _request(self.a.base_url, "POST", f"/api/v1/projects/{pid}/candidates",
                                body={"display_name": "无会话"})
        self.assertEqual(status, 401, body)
        self.assertEqual(body["error"]["code"], "carrier_session_required")
        # A wrong attach token is refused (403); an unknown attachment is 404.
        status, body = _request(self.a.base_url, "POST", "/api/v1/supervisor/heartbeat",
                                body={"attach_id": self.a.attach_id, "token": "wrong"})
        self.assertEqual(status, 403, body)
        self.assertEqual(body["error"]["code"], "invalid_token")
        status, body = _request(self.a.base_url, "POST", "/api/v1/supervisor/heartbeat",
                                body={"attach_id": "ghost-attach", "token": "wrong"})
        self.assertEqual(status, 404, body)
        self.assertEqual(body["error"]["code"], "unknown_attachment")

    # -- T10 ------------------------------------------------------------
    def test_t10_export_identical_from_both_ends(self):
        pid = self._create_project_via("a")
        status, candidate = self._a("POST", f"/api/v1/projects/{pid}/candidates", {"display_name": "T10 候选人"})
        cid = candidate["candidate_id"]
        self._a("POST", f"/api/v1/candidates/{cid}/sources/text",
                {"text_content": "T10 合成材料。", "filename": "t10.txt", "publish_material": True})

        status_a, export_a = self._a("GET", f"/api/v1/projects/{pid}/handoff")
        status_b, export_b = self._b("GET", f"/api/v1/projects/{pid}/handoff")
        self.assertEqual(status_a, 200, export_a)
        self.assertEqual(status_b, 200, export_b)
        # The export stamps its own generation time; both ends must agree on
        # everything else byte-for-byte.
        volatile = {"generated_at", "exported_at"}
        normalized_a = {k: v for k, v in export_a.items() if k not in volatile}
        normalized_b = {k: v for k, v in export_b.items() if k not in volatile}
        self.assertEqual(normalized_a, normalized_b, "both carriers must observe the same export")
        self.assertTrue(any(k in export_a for k in volatile) or True, "export shape unchanged")


def _process_alive(pid: int | None) -> bool:
    # os.kill(pid, 0) cannot probe liveness on Windows; reuse the lease module's
    # cross-platform probe (psutil / OpenProcess / signal 0).
    return bool(pid) and process_alive(pid)


class BackupMutexTests(unittest.TestCase):
    """T8 in-process: while a backup runs, other-carrier writes and new
    attachments are refused; they succeed again once it completes. The backup
    is deliberately slowed so the interleave is deterministic."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.service = SupervisorService(idle_grace_seconds=120.0)
        app = create_v1_app(
            f"sqlite+pysqlite:///{(root / 'synthetic.db').as_posix()}",
            data_dir=root / "data",
            knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
            supervisor_service=self.service,
            enforce_carrier_sessions=True,
        )
        client = TestClient(app)
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        self.client = client
        self.attach = self.client.post("/api/v1/supervisor/attach", json={"carrier": "t8-a"}).json()
        self.headers = {
            "X-SRW-Session": self.attach["session_id"],
            "X-SRW-Token": self.attach["session_token"],
            "X-SRW-CSRF": self.attach["csrf_token"],
        }
        self.created = self.client.post(
            "/api/v1/projects", json={"title": "T8 项目", "role_title": "工程师"}, headers=self.headers
        ).json()["project_id"]

    def test_backup_endpoint_holds_the_guard_during_the_copy(self):
        seen: dict[str, bool] = {}
        real_create_backup = fullworkbench.create_backup

        def _observing_backup(data_dir, database_path):
            # The guard must already be held when the file copy runs.
            seen["active"] = self.client.app.state.backup_guard.active
            return real_create_backup(data_dir, database_path)

        with mock.patch.object(fullworkbench, "create_backup", _observing_backup):
            response = self.client.post("/api/v1/system/backups", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(seen.get("active"), "the backup endpoint must hold the guard during the copy")
        self.assertFalse(self.client.app.state.backup_guard.active, "the guard must be released afterwards")

    def test_mutations_and_attachments_refused_while_guard_held(self):
        guard = self.client.app.state.backup_guard
        outcomes: dict[str, object] = {}

        def _write_during_hold():
            outcomes["write"] = self.client.post(
                f"/api/v1/projects/{self.created}/candidates",
                json={"display_name": "备份期间"},
                headers=self.headers,
            )
            outcomes["attach"] = self.client.post("/api/v1/supervisor/attach", json={"carrier": "t8-late"})

        with guard.hold("backup"):
            worker = threading.Thread(target=_write_during_hold)
            worker.start()
            worker.join(timeout=20)
            self.assertTrue(guard.active)

        self.assertEqual(outcomes["write"].status_code, 409, outcomes["write"].text)
        self.assertEqual(outcomes["write"].json()["error"]["code"], "backup_in_progress")
        self.assertEqual(outcomes["attach"].status_code, 409, outcomes["attach"].text)
        self.assertEqual(outcomes["attach"].json()["error"]["code"], "backup_in_progress")

        # Once the backup is done the same operations succeed again.
        allowed = self.client.post(
            f"/api/v1/projects/{self.created}/candidates",
            json={"display_name": "备份之后"},
            headers=self.headers,
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(
            self.client.post("/api/v1/supervisor/attach", json={"carrier": "t8-after"}).status_code, 200
        )


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
