from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app
from srw.runtime.maintenance import cleanup_stale_backup_artifacts
from scripts.check_release_truth import validate as validate_release_truth
from scripts.resource_probe import is_sqlite_fd_target, residual_is_clean, resource_residual

ROOT = Path(__file__).resolve().parents[1]


class Convergence09Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.knowledge = create_minimal_knowledge_tree(self.root / "knowledge" / "active")

    def tearDown(self):
        self.tmp.cleanup()

    def _app(self):
        return create_v1_app(
            f"sqlite+pysqlite:///{(self.root/'test.db').as_posix()}",
            data_dir=self.data,
            knowledge_dir=self.knowledge,
            frontend_dist=ROOT / "frontend" / "dist",
        )

    def test_importing_app_factory_has_no_user_data_side_effect(self):
        cwd = self.root / "fresh-import"
        cwd.mkdir()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "backend")
        code = "from srw.api.app import create_v1_app; print(create_v1_app.__name__)"
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "create_v1_app")
        self.assertFalse((cwd / "data").exists())

    def test_local_only_boundary_rejects_lan_host(self):
        with TestClient(self._app()) as client:
            allowed = client.get("/api/v1/runtime/live", headers={"host": "127.0.0.1:8000"})
            blocked = client.get("/api/v1/runtime/live", headers={"host": "192.168.1.9:8000"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("本机地址", blocked.json()["detail"])

    def test_cross_origin_browser_mutation_is_rejected_but_same_origin_is_allowed(self):
        app = self._app()
        payload = {"title": "同源测试", "role_title": "工程师", "brief_summary": ""}
        with TestClient(app) as client:
            same = client.post(
                "/api/v1/projects",
                headers={"host": "testserver", "origin": "http://testserver"},
                json=payload,
            )
            blocked = client.post(
                "/api/v1/projects",
                headers={"host": "testserver", "origin": "https://attacker.example"},
                json=payload,
            )
            other_port = client.post(
                "/api/v1/projects",
                headers={"host": "127.0.0.1:8000", "origin": "http://127.0.0.1:9999"},
                json=payload,
            )
        self.assertEqual(same.status_code, 200, same.text)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(other_port.status_code, 403)

    def test_startup_cleanup_removes_only_known_stale_backup_artifacts(self):
        self.data.mkdir(parents=True)
        backups = self.data / "backups"
        backups.mkdir()
        stale_dir = self.data / ".backup-snapshot-old"
        stale_dir.mkdir(); (stale_dir / "srw_v1.db").write_bytes(b"old")
        restore_dir = self.data / ".restore-staging-old"
        restore_dir.mkdir(); (restore_dir / "tmp").write_bytes(b"old")
        stale_import = backups / ".backup-import-deadbeef"
        stale_import.write_bytes(b"tmp")
        partial = backups / "unfinished.zip.partial"
        partial.write_bytes(b"tmp")
        valid = backups / "keep.zip"
        valid.write_bytes(b"valid")

        result = cleanup_stale_backup_artifacts(self.data)

        self.assertFalse(stale_dir.exists())
        self.assertFalse(restore_dir.exists())
        self.assertFalse(stale_import.exists())
        self.assertFalse(partial.exists())
        self.assertTrue(valid.exists())
        self.assertEqual(result, {"directories": 2, "files": 2})

    def test_backup_contains_business_restore_data_not_transient_outputs(self):
        app = self._app()
        with TestClient(app) as client:
            for relative in ("logs/app.log", "exports/project.zip", "diagnostics/diagnostics.zip"):
                path = self.data / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"not restore truth")
            response = client.post("/api/v1/system/backups")
            self.assertEqual(response.status_code, 200, response.text)
            archive = self.data / "backups" / response.json()["filename"]
            with zipfile.ZipFile(archive) as zf:
                names = set(zf.namelist())
        self.assertIn("data/srw_v1.db", names)
        self.assertNotIn("data/logs/app.log", names)
        self.assertNotIn("data/exports/project.zip", names)
        self.assertNotIn("data/diagnostics/diagnostics.zip", names)

    def test_diagnostics_exposes_normalized_system_checks(self):
        with TestClient(self._app()) as client:
            response = client.get("/api/v1/system/diagnostics")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["overall_status"], "ok")
        checks = {row["name"]: row for row in payload["checks"]}
        for name in ("database_integrity", "data_directory", "frontend_assets", "background_tasks", "backups", "knowledge"):
            self.assertIn(name, checks)
        self.assertEqual(checks["database_integrity"]["status"], "ok")
        self.assertEqual(checks["frontend_assets"]["status"], "ok")
        self.assertTrue(payload["local_only"])
        self.assertEqual(payload["backup_retention"], 14)

    def test_sqlite_resource_probe_covers_db_sqlite_sqlite3_sidecars_and_deleted(self):
        accepted = [
            "/tmp/a.db", "/tmp/a.db-wal", "/tmp/a.db-shm", "/tmp/a.db-journal",
            "/tmp/a.sqlite", "/tmp/a.sqlite-wal", "/tmp/a.sqlite-shm", "/tmp/a.sqlite-journal",
            "/tmp/a.sqlite3", "/tmp/a.sqlite3-wal", "/tmp/a.sqlite3-shm", "/tmp/a.sqlite3-journal",
            "/tmp/a.db (deleted)",
        ]
        for value in accepted:
            self.assertTrue(is_sqlite_fd_target(value), value)
        self.assertFalse(is_sqlite_fd_target("/tmp/database.txt"))
        self.assertFalse(is_sqlite_fd_target("/tmp/file.db.backup"))

    def test_resource_residual_ignores_baseline_and_detects_new_resources(self):
        baseline = {
            "threads": [{"name": "environment", "daemon": False, "ident": 42}],
            "multiprocessing_children": [],
            "sqlite_open_files": ["/tmp/base.db"],
        }
        same = {
            "threads": [{"name": "environment", "daemon": False, "ident": 42}],
            "multiprocessing_children": [],
            "sqlite_open_files": ["/tmp/base.db"],
        }
        self.assertTrue(residual_is_clean(resource_residual(baseline, same)))
        leaked = {
            "threads": same["threads"] + [{"name": "leaked-daemon", "daemon": True, "ident": 99}],
            "multiprocessing_children": [{"name": "worker", "pid": 123}],
            "sqlite_open_files": ["/tmp/base.db", "/tmp/new.sqlite-wal"],
        }
        residual = resource_residual(baseline, leaked)
        self.assertFalse(residual_is_clean(residual))
        self.assertEqual(residual["threads"][0]["ident"], 99)
        self.assertEqual(residual["multiprocessing_children"][0]["pid"], 123)
        self.assertEqual(residual["sqlite_open_files"], ["/tmp/new.sqlite-wal"])

    def test_release_truth_files_are_internally_bound(self):
        self.assertEqual(validate_release_truth(), [])


if __name__ == "__main__":
    unittest.main()
