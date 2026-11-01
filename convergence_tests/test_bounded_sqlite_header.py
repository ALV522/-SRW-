"""#130 (second slice): the SQLite header probe must read 16 bytes, not the whole file.

Three call sites used ``path.read_bytes()[:16]``. Slicing happens *after* the read, so
the whole database was materialised in memory just to check a magic number: a 200 MB
user database or a large knowledge database spikes the process by its full size
during restore validation, portable migration and the native self-check.

Coverage note: ``_read_schema`` and ``validate_v1_database`` are the public entry
points, and ``self_check`` reaches the same helper through its knowledge loop. All
three are driven here with ``Path.read_bytes`` patched to raise, so a regression to
the whole-file read fails the test instead of quietly costing memory. The self-check
case stubs every gate before the knowledge loop and never touches a real knowledge
library.
"""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "backend"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import launch_alpha10  # noqa: E402
from srw.runtime import portable_migration  # noqa: E402

MAGIC = b"SQLite format 3\x00"
REVISION = "v1_0014"
KNOWLEDGE_LIBRARIES = ("taxonomy", "job_info", "competency", "market_reference", "reference")
PINNED_PACKAGES = {
    "SQLAlchemy": "2.0.43", "starlette": "0.47.3", "uvicorn": "0.35.0", "httpx": "0.28.1",
    "PyMuPDF": "1.26.4", "python-docx": "1.2.0", "openpyxl": "3.1.5",
    "python-multipart": "0.0.32",
}


def _make_database(path: Path, revision: str = REVISION) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT NOT NULL)")
        conn.execute("INSERT INTO v1_schema_meta VALUES (?)", (revision,))
        conn.commit()
    finally:
        conn.close()


def _forbidden_read_bytes():
    return mock.Mock(side_effect=AssertionError(
        "read_bytes() materialises the whole database just to check 16 bytes"))


class BoundedSqliteHeaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="srw-header-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_header_probe_never_reads_the_whole_file(self):
        db = self.root / "valid.db"
        _make_database(db)
        forbidden = _forbidden_read_bytes()
        with mock.patch.object(Path, "read_bytes", forbidden):
            self.assertEqual(portable_migration.validate_v1_database(db), REVISION)
            self.assertEqual(launch_alpha10._read_schema(db), REVISION)
            # The shared helper is what self_check's knowledge loop calls.
            self.assertTrue(launch_alpha10._has_sqlite_header(db))
        forbidden.assert_not_called()

    def test_large_non_sqlite_file_is_rejected(self):
        big = self.root / "payload.bin"
        big.write_bytes(b"\x00" * (4 * 1024 * 1024))
        with self.assertRaises(portable_migration.PortableMigrationError) as caught:
            portable_migration.validate_v1_database(big)
        self.assertIn("not valid SQLite", str(caught.exception))
        with self.assertRaises(RuntimeError) as caught_backup:
            launch_alpha10._read_schema(big)
        self.assertIn("invalid backup database", str(caught_backup.exception))

    def test_short_missing_and_directory_paths_are_rejected(self):
        short = self.root / "short.db"
        short.write_bytes(MAGIC[:8])
        directory = self.root / "directory.db"
        directory.mkdir()
        missing = self.root / "missing.db"

        for path in (short, directory):
            with self.subTest(path=path.name):
                with self.assertRaises(portable_migration.PortableMigrationError):
                    portable_migration.validate_v1_database(path)
                with self.assertRaises(RuntimeError):
                    launch_alpha10._read_schema(path)

        with self.subTest(path="missing"):
            with self.assertRaises(portable_migration.PortableMigrationError) as caught:
                portable_migration.validate_v1_database(missing)
            self.assertIn("not found", str(caught.exception))
            with self.assertRaises(RuntimeError):
                launch_alpha10._read_schema(missing)

    def test_unreadable_or_vanishing_file_fails_closed_without_a_traceback(self):
        # Windows access-denied and a file deleted between stat and open both arrive
        # as OSError here. They must degrade to the existing "invalid database"
        # verdict, not escape, and must not leave an empty database behind.
        db = self.root / "locked.db"
        _make_database(db)
        before = db.stat().st_size
        for error in (PermissionError(13, "access denied"), FileNotFoundError(2, "gone")):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(Path, "open", side_effect=error):
                    self.assertFalse(launch_alpha10._has_sqlite_header(db))
                    with self.assertRaises(portable_migration.PortableMigrationError) as caught:
                        portable_migration.validate_v1_database(db)
                    self.assertIn("not valid SQLite", str(caught.exception))
                    with self.assertRaises(RuntimeError) as caught_backup:
                        launch_alpha10._read_schema(db)
                    self.assertIn("invalid backup database", str(caught_backup.exception))
                self.assertEqual(db.stat().st_size, before)
                self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                                 ["locked.db"])

    def test_valid_header_with_corrupt_body_is_still_rejected(self):
        # A matching 16-byte magic is necessary but not sufficient: the quick_check /
        # schema read must still decide, and neither call site may report success.
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(MAGIC + b"\x00" * 4096)
        with self.assertRaises(portable_migration.PortableMigrationError) as caught:
            portable_migration.validate_v1_database(corrupt)
        self.assertIn("validation failed", str(caught.exception))
        with self.assertRaises(sqlite3.DatabaseError):
            launch_alpha10._read_schema(corrupt)

    def test_valid_database_still_passes_both_call_sites(self):
        db = self.root / "valid.db"
        _make_database(db)
        self.assertEqual(portable_migration.validate_v1_database(db), REVISION)
        self.assertEqual(launch_alpha10._read_schema(db), REVISION)

    def _self_check_fixture(self, *, bad_library: str | None = None):
        """Stub every gate before the knowledge loop; return a patch list."""
        root = self.root / "app"
        frontend = root / "frontend" / "dist"
        knowledge = root / "knowledge" / "active"
        (root / "backend" / "srw").mkdir(parents=True, exist_ok=True)
        (root / "backend" / "srw" / "release_state.json").write_text("{}", encoding="utf-8")
        frontend.mkdir(parents=True, exist_ok=True)
        for name in ("index.html", "app.js", "styles.css"):
            (frontend / name).write_text("", encoding="utf-8")
        for name in KNOWLEDGE_LIBRARIES:
            folder = knowledge / name
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / "knowledge.db"
            if name == bad_library:
                target.write_bytes(b"\x00" * 4096)
            else:
                target.write_bytes(MAGIC)

        import importlib.metadata as metadata

        return [
            mock.patch.object(sys, "version_info", (3, 12, 10)),
            mock.patch.object(metadata, "version", side_effect=lambda name: PINNED_PACKAGES[name]),
            mock.patch.object(launch_alpha10, "ROOT", root),
            mock.patch.object(launch_alpha10, "FRONTEND", frontend),
            mock.patch.object(launch_alpha10, "KNOWLEDGE", knowledge),
            mock.patch("srw.api.app.create_v1_app", return_value=mock.Mock()),
            mock.patch("srw.release.get_release_state",
                       return_value={"version": launch_alpha10.EXPECTED_VERSION,
                                     "schema_revision": launch_alpha10.EXPECTED_SCHEMA}),
        ]

    def _run_self_check(self, patches):
        buffer = io.StringIO()
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        forbidden = _forbidden_read_bytes()
        with mock.patch.object(Path, "read_bytes", forbidden), contextlib.redirect_stdout(buffer):
            status = launch_alpha10.self_check()
        forbidden.assert_not_called()
        return status, json.loads(buffer.getvalue())

    def test_self_check_accepts_valid_knowledge_headers_without_full_reads(self):
        status, payload = self._run_self_check(self._self_check_fixture())
        self.assertEqual(status, 0, payload)
        self.assertTrue(payload["ok"], payload)

    def test_self_check_rejects_a_bad_knowledge_database_without_full_reads(self):
        status, payload = self._run_self_check(self._self_check_fixture(bad_library="taxonomy"))
        self.assertEqual(status, 1, payload)
        self.assertFalse(payload["ok"], payload)
        self.assertIn("knowledge database invalid: taxonomy", payload["error"])


if __name__ == "__main__":
    unittest.main()
