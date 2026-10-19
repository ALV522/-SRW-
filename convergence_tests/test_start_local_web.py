"""No-network, no-real-data regressions for the local Core + Browser launcher."""
from __future__ import annotations

import sqlite3
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
        with sqlite3.connect(self.workspace / "data" / "srw_v1.db") as conn:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT)")
            conn.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014')")
        self.assertTrue(self.check())
        self.assertEqual(self.check(reuse=True), [])
        self.assertTrue(self.check(synthetic=True))

    def test_blocks_native_host_lock(self):
        (self.workspace / "data").mkdir(parents=True)
        (self.workspace / "data" / "app.lock").write_bytes(b"HOST OWNS THIS WORKSPACE")
        self.assertTrue(any("app.lock" in e for e in self.check(reuse=True)))

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
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT)")
            conn.execute("INSERT INTO v1_schema_meta VALUES ('v1_9999')")
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
