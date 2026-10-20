"""Cross-carrier workspace lease: one workspace admits exactly one writer.

These regressions run on a real temporary filesystem. They do not open SQLite,
do not touch a user workspace and do not claim Windows WPF or browser
acceptance; they prove the single-writer contract that both carriers consume.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from srw.workspace_lease import (
    ABSENT,
    ACTIVE,
    CORRUPT,
    FOREIGN,
    FRESH_INCOMPLETE_WINDOW_SECONDS,
    LEASE_DIRECTORY_NAME,
    LEASE_METADATA_NAME,
    STALE,
    WorkspaceLease,
    WorkspaceLeaseError,
    inspect_lease,
    lease_directory,
    process_alive,
)

DEAD_PID = 4_000_000


def host_shaped_metadata(data_dir: Path, pid: int, edition: str = "windows") -> dict:
    """Mirror of the JSON shape written by WorkspaceLease.cs (schema v2)."""
    return {
        "schema_version": 2,
        "pid": pid,
        "port": 8765,
        "version": "1.0.0-alpha10-convergence11",
        "release_id": "1.0.0-alpha10-convergence11",
        "instance_id": "host-instance",
        "session_id": "host-session",
        "edition": edition,
        "started_at": "2026-10-20T00:00:00+00:00",
        "process_started_at_utc": None,
        "hostname": "SYNTHETIC-HOST",
        "data_dir": str(data_dir),
        "data_root_hash": "0" * 64,
    }


class WorkspaceLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-workspace-lease-")
        self.data = Path(self.tmp.name) / "workspace" / "data"

    def tearDown(self):
        self.tmp.cleanup()

    def lease(self, **kwargs) -> WorkspaceLease:
        kwargs.setdefault("edition", "local-web")
        return WorkspaceLease(self.data, **kwargs)

    def test_absent_workspace_reports_absent_without_creating_anything(self):
        self.assertEqual(inspect_lease(self.data).state, ABSENT)
        self.assertFalse(self.data.exists(), "inspection must not create the data directory")

    def test_acquire_creates_contract_shaped_lease(self):
        with self.lease(port=8765) as lease:
            self.assertTrue(lease.held)
            directory = lease_directory(self.data)
            self.assertTrue(directory.is_dir())
            payload = json.loads((directory / LEASE_METADATA_NAME).read_text(encoding="utf-8"))
            self.assertEqual(
                set(payload),
                {
                    "schema_version", "pid", "port", "version", "release_id",
                    "instance_id", "session_id", "edition", "started_at",
                    "process_started_at_utc", "hostname", "data_dir", "data_root_hash",
                },
                "lease metadata must stay byte-compatible with the Windows Host reader",
            )
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["pid"], os.getpid())
            self.assertEqual(payload["edition"], "local-web")
            self.assertEqual(payload["port"], 8765)
            self.assertIsNone(
                payload["process_started_at_utc"],
                "null keeps the .NET reader fail-closed instead of letting it evict a live lease",
            )
        self.assertFalse(lease_directory(self.data).exists(), "release must remove the lease")

    def test_second_writer_on_the_same_workspace_is_refused(self):
        holder = self.lease().acquire()
        try:
            with self.assertRaises(WorkspaceLeaseError) as caught:
                self.lease().acquire()
            self.assertIn("INSTANCE_ALREADY_RUNNING", str(caught.exception))
            self.assertIn(str(os.getpid()), str(caught.exception))
        finally:
            holder.release()

    def test_host_shaped_live_lease_blocks_the_browser_core(self):
        directory = lease_directory(self.data)
        directory.mkdir(parents=True)
        (directory / LEASE_METADATA_NAME).write_text(
            json.dumps(host_shaped_metadata(self.data, os.getpid())), encoding="utf-8"
        )
        inspection = inspect_lease(self.data)
        self.assertEqual(inspection.state, ACTIVE)
        self.assertTrue(inspection.blocks)
        self.assertEqual(inspection.holder.edition, "windows")
        with self.assertRaises(WorkspaceLeaseError) as caught:
            self.lease().acquire()
        self.assertIn("windows", str(caught.exception))
        self.assertTrue(
            (directory / LEASE_METADATA_NAME).is_file(),
            "a live foreign lease must never be cleared",
        )

    def test_lease_of_a_dead_process_is_recovered_atomically(self):
        directory = lease_directory(self.data)
        directory.mkdir(parents=True)
        (directory / LEASE_METADATA_NAME).write_text(
            json.dumps(host_shaped_metadata(self.data, DEAD_PID)), encoding="utf-8"
        )
        self.assertEqual(inspect_lease(self.data).state, STALE)
        with self.lease() as lease:
            self.assertTrue(lease.held)
            payload = json.loads(
                (directory / LEASE_METADATA_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["pid"], os.getpid())
            self.assertEqual(payload["edition"], "local-web")
        self.assertFalse(directory.exists())

    def test_metadata_less_directory_is_only_recovered_after_the_fresh_window(self):
        directory = lease_directory(self.data)
        directory.mkdir(parents=True)
        self.assertEqual(inspect_lease(self.data).state, ACTIVE)
        with self.assertRaises(WorkspaceLeaseError):
            self.lease().acquire()

        stale_epoch = time.time() - FRESH_INCOMPLETE_WINDOW_SECONDS - 60
        os.utime(directory, (stale_epoch, stale_epoch))
        self.assertEqual(inspect_lease(self.data).state, STALE)
        with self.lease() as lease:
            self.assertTrue(lease.held)

    def test_plain_file_lock_is_foreign_and_never_removed(self):
        self.data.mkdir(parents=True)
        foreign = self.data / LEASE_DIRECTORY_NAME
        foreign.write_bytes(b"HOST OWNS THIS WORKSPACE")
        inspection = inspect_lease(self.data)
        self.assertEqual(inspection.state, FOREIGN)
        with self.assertRaises(WorkspaceLeaseError) as caught:
            self.lease().acquire()
        self.assertIn("WORKSPACE_LEASE_UNUSABLE", str(caught.exception))
        self.assertEqual(foreign.read_bytes(), b"HOST OWNS THIS WORKSPACE")

    def test_corrupt_metadata_blocks_instead_of_being_silently_replaced(self):
        directory = lease_directory(self.data)
        directory.mkdir(parents=True)
        (directory / LEASE_METADATA_NAME).write_text("{not json", encoding="utf-8")
        self.assertEqual(inspect_lease(self.data).state, CORRUPT)
        with self.assertRaises(WorkspaceLeaseError):
            self.lease().acquire()
        self.assertEqual((directory / LEASE_METADATA_NAME).read_text(encoding="utf-8"), "{not json")

    def test_metadata_without_usable_pid_is_corrupt(self):
        directory = lease_directory(self.data)
        directory.mkdir(parents=True)
        (directory / LEASE_METADATA_NAME).write_text(json.dumps({"pid": "x"}), encoding="utf-8")
        self.assertEqual(inspect_lease(self.data).state, CORRUPT)

    def test_symlinked_lease_path_is_foreign(self):
        self.data.mkdir(parents=True)
        target = Path(self.tmp.name) / "elsewhere"
        target.mkdir()
        link = self.data / LEASE_DIRECTORY_NAME
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is not permitted on this host")
        if not link.is_symlink():
            self.skipTest("this filesystem does not report symlinks")
        self.assertEqual(inspect_lease(self.data).state, FOREIGN)
        with self.assertRaises(WorkspaceLeaseError):
            self.lease().acquire()

    def test_release_never_evicts_a_lease_owned_by_another_instance(self):
        first = self.lease(instance_id="first").acquire()
        metadata_path = lease_directory(self.data) / LEASE_METADATA_NAME
        replacement = json.loads(metadata_path.read_text(encoding="utf-8"))
        replacement["instance_id"] = "second"
        metadata_path.write_text(json.dumps(replacement), encoding="utf-8")

        first.release()

        self.assertTrue(metadata_path.is_file(), "release must only drop its own lease")
        self.assertEqual(
            json.loads(metadata_path.read_text(encoding="utf-8"))["instance_id"], "second"
        )

    def test_unknown_edition_is_rejected_before_any_filesystem_change(self):
        with self.assertRaises(ValueError):
            WorkspaceLease(self.data, edition="cloud")
        self.assertFalse(self.data.exists())

    def test_liveness_probe_agrees_with_the_reconciled_contract(self):
        self.assertTrue(process_alive(os.getpid()))
        self.assertFalse(process_alive(DEAD_PID))
        self.assertFalse(process_alive(0))
        self.assertFalse(process_alive(-1))


if __name__ == "__main__":
    unittest.main()
