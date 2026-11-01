"""#130 (second slice): the SQLite header probe must read 16 bytes, not the whole file.

Three call sites used ``path.read_bytes()[:16]``. Slicing happens *after* the read, so
the whole database is materialised in memory just to check a magic number: a 200 MB
user database or a large knowledge database spikes the process by its full size
during restore validation and portable migration.

The oracles below are behavioural, not implementation-shaped: they drive the real
call sites and fail if anything reaches for ``Path.read_bytes``. The rejection
messages for non-SQLite, truncated, missing and directory paths must not change.
"""
from __future__ import annotations

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


def _make_database(path: Path, revision: str = REVISION) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT NOT NULL)")
        conn.execute("INSERT INTO v1_schema_meta VALUES (?)", (revision,))
        conn.commit()
    finally:
        conn.close()


class BoundedSqliteHeaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="srw-header-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_header_probe_never_reads_the_whole_file(self):
        db = self.root / "valid.db"
        _make_database(db)
        forbidden = mock.Mock(side_effect=AssertionError(
            "read_bytes() materialises the whole database just to check 16 bytes"))
        with mock.patch.object(Path, "read_bytes", forbidden):
            self.assertEqual(portable_migration.validate_v1_database(db), REVISION)
            self.assertEqual(launch_alpha10._read_schema(db), REVISION)
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

    def test_valid_database_still_passes_both_call_sites(self):
        db = self.root / "valid.db"
        _make_database(db)
        self.assertEqual(portable_migration.validate_v1_database(db), REVISION)
        self.assertEqual(launch_alpha10._read_schema(db), REVISION)


if __name__ == "__main__":
    unittest.main()
