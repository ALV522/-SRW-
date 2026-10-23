"""Schema v1_0015 migration path (ADR-0003 phase 2).

An existing v1_0014 workspace must open under v1_0015 code: the migration
branch runs, the revision moves, and the new carrier_session table exists.
A database at an unknown revision is still refused.
"""
from __future__ import annotations

import tempfile
from contextlib import closing
import unittest
from pathlib import Path

from srw.runtime.db.base import V1Base
from srw.runtime.db.schema import V1_SCHEMA_REVISION, create_v1_schema
from srw.runtime.db.session import create_v1_engine


class SchemaMigrationTests(unittest.TestCase):
    def test_current_revision_is_v1_0015(self):
        self.assertEqual(V1_SCHEMA_REVISION, "v1_0015")

    def test_v1_0014_database_migrates_and_gains_carrier_session(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            with closing(sqlite3.connect(db_path)) as connection:
                # Simulate a pre-v1_0015 workspace: meta at the old revision and
                # none of the tables the migration branch would create.
                connection.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT, created_at DATETIME)")
                connection.execute("INSERT INTO v1_schema_meta VALUES ('v1_0014', '2026-10-21T00:00:00')")
                connection.commit()

            engine = create_v1_engine(f"sqlite+pysqlite:///{db_path.as_posix()}")
            try:
                create_v1_schema(engine)
                with engine.connect() as connection:
                    revision = connection.exec_driver_sql(
                        "SELECT schema_revision FROM v1_schema_meta LIMIT 1"
                    ).scalar_one()
                    tables = set(
                        connection.exec_driver_sql(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).scalars()
                    )
                self.assertEqual(revision, "v1_0015")
                self.assertIn("carrier_session", tables)
                self.assertIn("project", tables)
            finally:
                engine.dispose()

    def test_unknown_revision_is_refused(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "future.db"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("CREATE TABLE v1_schema_meta (schema_revision TEXT, created_at DATETIME)")
                connection.execute("INSERT INTO v1_schema_meta VALUES ('v9_9999', '2026-10-21T00:00:00')")
                connection.commit()
            engine = create_v1_engine(f"sqlite+pysqlite:///{db_path.as_posix()}")
            try:
                with self.assertRaises(RuntimeError):
                    create_v1_schema(engine)
            finally:
                engine.dispose()

    def test_fresh_database_gets_carrier_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_v1_engine(f"sqlite+pysqlite:///{(Path(tmp) / 'fresh.db').as_posix()}")
            try:
                create_v1_schema(engine)
                self.assertIn("carrier_session", V1Base.metadata.tables)
                with engine.connect() as connection:
                    exists = connection.exec_driver_sql(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='carrier_session'"
                    ).scalar()
                self.assertEqual(exists, "carrier_session")
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
