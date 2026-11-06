"""Synthetic wheelhouse byte-lock contract. No package/network dependency."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.verify_windows_wheelhouse_lock import WheelLockError, read_lock, verify


class WindowsWheelLockTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="srw-wheel-lock-synthetic-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.wheels = self.root / "wheels"
        self.wheels.mkdir()
        self.lock = self.root / "lock.sha256"
        self.write_wheel("alpha-1.0-py3-none-any.whl", b"synthetic alpha")
        self.write_wheel("beta-2.0-py3-none-any.whl", b"synthetic beta")
        self.save_lock()

    def write_wheel(self, name: str, data: bytes) -> None:
        (self.wheels / name).write_bytes(data)

    def save_lock(self) -> None:
        rows = []
        for path in sorted(self.wheels.glob("*.whl")):
            rows.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name)
        self.lock.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_real_byte_hashes_and_generated_inventory_are_accepted(self) -> None:
        result = verify(self.wheels, self.lock)
        self.assertEqual(result["status"], "PINNED_WINDOWS_WHEELS_VERIFIED")
        self.assertEqual(result["wheel_count"], 2)
        (self.wheels / "WHEELHOUSE.sha256").write_text(
            self.lock.read_text(encoding="utf-8"), encoding="utf-8"
        )
        self.assertEqual(result, verify(self.wheels, self.lock))

    def test_same_filename_modified_bytes_is_rejected(self) -> None:
        self.write_wheel("alpha-1.0-py3-none-any.whl", b"tampered")
        with self.assertRaisesRegex(WheelLockError, "wheel bytes changed"):
            verify(self.wheels, self.lock)

    def test_missing_and_extra_wheel_are_rejected(self) -> None:
        item = self.wheels / "beta-2.0-py3-none-any.whl"
        data = item.read_bytes()
        item.unlink()
        with self.assertRaisesRegex(WheelLockError, "filename set"):
            verify(self.wheels, self.lock)
        item.write_bytes(data)
        self.write_wheel("gamma-3.0-py3-none-any.whl", b"unreviewed")
        with self.assertRaisesRegex(WheelLockError, "filename set"):
            verify(self.wheels, self.lock)

    def test_unlisted_non_wheel_file_is_rejected(self) -> None:
        (self.wheels / "surprise.txt").write_text("synthetic")
        with self.assertRaisesRegex(WheelLockError, "unlisted file"):
            verify(self.wheels, self.lock)

    def test_unsafe_or_invalid_lock_entry_is_rejected(self) -> None:
        self.lock.write_text("0" * 64 + "  ../escape.whl\n")
        with self.assertRaisesRegex(WheelLockError, "invalid wheel lock entry"):
            read_lock(self.lock)
        self.lock.write_text("z" * 64 + "  alpha.whl\n")
        with self.assertRaisesRegex(WheelLockError, "invalid wheel lock entry"):
            read_lock(self.lock)

    def test_case_collision_and_unsorted_lock_are_rejected(self) -> None:
        self.lock.write_text(
            "0" * 64 + "  Alpha.whl\n" + "1" * 64 + "  alpha.whl\n"
        )
        with self.assertRaisesRegex(WheelLockError, "case-colliding"):
            read_lock(self.lock)
        self.lock.write_text(
            "0" * 64 + "  beta.whl\n" + "1" * 64 + "  alpha.whl\n"
        )
        with self.assertRaisesRegex(WheelLockError, "must be sorted"):
            read_lock(self.lock)

    def test_symlink_wheel_is_rejected_where_supported(self) -> None:
        alias = self.wheels / "other-1.0.whl"
        try:
            alias.symlink_to(self.wheels / "alpha-1.0-py3-none-any.whl")
        except (OSError, NotImplementedError):
            self.skipTest("platform disallows synthetic symlink")
        with self.assertRaisesRegex(WheelLockError, "symlink"):
            verify(self.wheels, self.lock)


if __name__ == "__main__":
    unittest.main()
