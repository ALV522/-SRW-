"""Actual OS parent/child lease handshake (synthetic Host, not WPF GUI)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from srw.workspace_lease import ACTIVE, ABSENT, WorkspaceLease, inspect_lease

ROOT = Path(__file__).resolve().parents[1]
CHILD_CODE = (
    "import sys\n"
    "from pathlib import Path\n"
    "from srw.workspace_lease import require_parent_host_lease\n"
    "require_parent_host_lease(Path(sys.argv[1]).resolve(), port=8791, "
    "instance_id=sys.argv[2], session_id=sys.argv[3])\n"
    "print('CHILD_LEASE_VERIFIED')\n"
)


class HostParentProcessContractTests(unittest.TestCase):
    def _child(self, data: Path, session: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "backend")
        return subprocess.run(
            [sys.executable, "-B", "-c", CHILD_CODE, str(data), "synthetic-host", session],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
        )

    def test_real_child_matches_owning_parent_and_releases_without_lock_drift(self):
        with tempfile.TemporaryDirectory(prefix="srw-parent-child-") as root:
            data = Path(root) / "workspace" / "data"
            with WorkspaceLease(data, edition="windows", port=8791,
                                instance_id="synthetic-host", session_id="synthetic-session"):
                result = self._child(data, "synthetic-session")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "CHILD_LEASE_VERIFIED")
                self.assertEqual(inspect_lease(data).state, ACTIVE)
            self.assertEqual(inspect_lease(data).state, ABSENT)

    def test_real_child_rejects_forged_session_without_eviction(self):
        with tempfile.TemporaryDirectory(prefix="srw-parent-child-") as root:
            data = Path(root) / "workspace" / "data"
            with WorkspaceLease(data, edition="windows", port=8791,
                                instance_id="synthetic-host", session_id="synthetic-session"):
                result = self._child(data, "forged-session")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("HOST_WORKSPACE_INVALID", result.stderr)
                self.assertNotIn("CHILD_LEASE_VERIFIED", result.stdout)
                self.assertEqual(inspect_lease(data).state, ACTIVE)
            self.assertEqual(inspect_lease(data).state, ABSENT)


if __name__ == "__main__":
    unittest.main()
