"""No-network, no-real-data regressions for the local Core + Browser launcher."""
from __future__ import annotations

import sqlite3
from contextlib import closing
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.start_local_web import production_knowledge_errors, workspace_errors


class LocalWebLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-local-web-unit-")
        self.root = Path(self.tmp.name) / "source"
        self.root.mkdir()
        self.workspace = Path(self.tmp.name) / "isolated"

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, path=None, *, reuse=False, synthetic=False):
        return workspace_errors(path or self.workspace, reuse=reuse, synthetic=synthetic,
                                source_root=self.root)

    def test_fresh_explicit_workspaces_are_allowed(self):
        self.assertEqual(self.check(), [])
        self.workspace.mkdir()
        self.assertEqual(self.check(), [])
        self.assertEqual(self.check(synthetic=True), [])

    def test_blocks_live_app_tree_or_parent(self):
        self.assertTrue(self.check(self.root))
        self.assertTrue(self.check(self.root / "data"))
        self.assertTrue(self.check(self.root.parent))

    def test_blocks_implicit_access_to_existing_user_data(self):
        (self.workspace / "data").mkdir(parents=True)
        with closing(sqlite3.connect(self.workspace / "data" / "srw_v1.db")) as conn:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT)")
            conn.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014')")
            conn.commit()
        self.assertTrue(self.check())
        self.assertEqual(self.check(reuse=True), [])
        self.assertTrue(self.check(synthetic=True))

    def test_blocks_native_host_lock(self):
        (self.workspace / "data").mkdir(parents=True)
        (self.workspace / "data" / "app.lock").write_bytes(b"HOST OWNS THIS WORKSPACE")
        self.assertTrue(any("app.lock" in e for e in self.check(reuse=True)))

    def test_live_host_lease_blocks_the_browser_core(self):
        lease_dir = self.workspace / "data" / "app.lock"
        lease_dir.mkdir(parents=True)
        (lease_dir / "instance.json").write_text(
            json.dumps({"schema_version": 2, "pid": os.getpid(), "edition": "windows",
                        "instance_id": "live-host"}), encoding="utf-8")
        errors = [e for e in self.check() if "app.lock" in e]
        self.assertTrue(errors, "a live Windows Host lease must block the browser Core")
        self.assertIn("windows", errors[0])

    def test_stale_host_lease_does_not_block_a_new_browser_core(self):
        lease_dir = self.workspace / "data" / "app.lock"
        lease_dir.mkdir(parents=True)
        (lease_dir / "instance.json").write_text(
            json.dumps({"schema_version": 2, "pid": 4_000_000, "edition": "windows",
                        "instance_id": "crashed-host"}), encoding="utf-8")
        self.assertFalse([e for e in self.check() if "app.lock" in e],
                         "a lease whose owner is gone must be recoverable, not a permanent block")

    def test_requires_real_existing_database_for_reuse(self):
        self.workspace.mkdir()
        self.assertTrue(self.check(reuse=True))
        self.assertTrue(self.check(synthetic=True, reuse=True))

    def test_rejects_invalid_or_incompatible_existing_db(self):
        (self.workspace / "data").mkdir(parents=True)
        db = self.workspace / "data" / "srw_v1.db"
        db.write_bytes(b"NOT A SQLITE DB")
        self.assertTrue(any("integrity/schema" in e for e in self.check(reuse=True)))
        db.unlink()
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT)")
            conn.execute("INSERT INTO v1_schema_meta VALUES ('v1_9999')")
            conn.commit()
        self.assertTrue(any("integrity/schema" in e for e in self.check(reuse=True)))

    def test_rejects_symlink_database(self):
        (self.workspace / "data").mkdir(parents=True)
        external = Path(self.tmp.name) / "external.sqlite"
        external.write_bytes(b"DO NOT FOLLOW")
        try:
            (self.workspace / "data" / "srw_v1.db").symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unsupported")
        self.assertTrue(any("symbolic links" in e for e in self.check(reuse=True)))

    def test_missing_knowledge_is_not_silently_replaced_by_synthetic(self):
        self.assertTrue(production_knowledge_errors(self.workspace))


if __name__ == "__main__":
    unittest.main()
