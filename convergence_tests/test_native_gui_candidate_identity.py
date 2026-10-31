"""#42 GUI v2: the report may only bind the candidate ZIP that was really exercised.

Pure synthetic oracles: no WPF process, no Native payload, no user data. The real
Windows run re-verifies the same contract end to end.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import accept_rebuilt_native_gui as gui
from scripts.native_payload import PayloadError

SOURCE = "a" * 40


def digest_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CandidateIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="srw-gui-identity-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "candidate"
        self.root.mkdir()
        self.payload = b"synthetic candidate archive bytes"
        self.archive = Path(self._tmp.name) / "candidate.zip"
        self.archive.write_bytes(self.payload)
        self.digest = digest_of(self.payload)

    # -- helpers ---------------------------------------------------------
    def accept(self, *, archive=None, expected=None, static=None):
        calls = static if static is not None else [
            {"zip_sha256": self.digest, "source_git_sha": SOURCE},
            {"zip_sha256": self.digest, "source_git_sha": SOURCE},
        ]
        with mock.patch.object(gui, "inspect_rebuilt", side_effect=calls) as inspect, \
                mock.patch.object(gui, "run_gui", return_value=[{"cycle": 1}]) as run:
            result = gui.accept_candidate(root=self.root, timeout=60, cycles=1,
                                          archive=archive, expected_sha256=expected)
        return result, inspect, run

    # -- v1 stays exactly as before --------------------------------------
    def test_without_zip_the_report_stays_v1_and_unbound(self):
        result, inspect, _ = self.accept(static=[{"zip_sha256": None, "source_git_sha": SOURCE}])
        self.assertEqual(result["schema"], "srw.rebuilt-native-gui-acceptance.v1")
        self.assertNotIn("candidate_sha256", result)
        self.assertNotIn("full_candidate_identity_bound", result)
        self.assertEqual(inspect.call_count, 1, "v1 must keep a single static inspection")

    # -- half-supplied pair is an error, not a fallback -------------------
    def test_zip_without_digest_is_rejected(self):
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=self.archive)
        self.assertIn("supplied together", str(caught.exception))

    def test_digest_without_zip_is_rejected(self):
        with self.assertRaises(PayloadError) as caught:
            self.accept(expected=self.digest)
        self.assertIn("supplied together", str(caught.exception))

    # -- digest shape ----------------------------------------------------
    def test_uppercase_digest_is_rejected(self):
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=self.archive, expected=self.digest.upper())
        self.assertIn("64 lowercase hex", str(caught.exception))

    def test_short_and_non_hex_digests_are_rejected(self):
        for bad in (self.digest[:63], self.digest[:-1] + "g", " " + self.digest[1:]):
            with self.subTest(digest=bad[:8]):
                with self.assertRaises(PayloadError) as caught:
                    self.accept(archive=self.archive, expected=bad)
                self.assertIn("64 lowercase hex", str(caught.exception))

    # -- archive presence / type ----------------------------------------
    def test_missing_archive_is_rejected(self):
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=Path(self._tmp.name) / "absent.zip", expected=self.digest)
        self.assertIn("regular file", str(caught.exception))

    def test_directory_instead_of_archive_is_rejected(self):
        directory = Path(self._tmp.name) / "a-directory.zip"
        directory.mkdir()
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=directory, expected=self.digest)
        self.assertIn("regular file", str(caught.exception))

    def test_symlinked_archive_is_rejected(self):
        link = Path(self._tmp.name) / "link.zip"
        try:
            os.symlink(self.archive, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not permitted on this runner")
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=link, expected=self.digest)
        self.assertIn("symlink", str(caught.exception))

    def test_symlink_branch_is_covered_even_without_symlink_privileges(self):
        # Windows dev boxes often cannot create symlinks, which silently skipped the
        # real case above. Exercise the same guard deterministically on every OS.
        fake = mock.Mock()
        fake.is_symlink.return_value = True
        fake.is_file.return_value = True
        with self.assertRaises(PayloadError) as caught:
            gui.resolve_candidate_archive(fake, self.digest)
        self.assertIn("symlink", str(caught.exception))

    # -- digest must match the bytes actually supplied -------------------
    def test_digest_mismatch_is_rejected(self):
        other = digest_of(b"some other candidate")
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=self.archive, expected=other)
        self.assertIn("SHA-256 mismatch", str(caught.exception))

    # -- the bound path ---------------------------------------------------
    def test_bound_run_emits_v2_and_checks_identity_twice(self):
        result, inspect, run = self.accept(archive=self.archive, expected=self.digest)
        self.assertEqual(result["schema"], "srw.rebuilt-native-gui-acceptance.v2")
        self.assertEqual(result["candidate_sha256"], self.digest)
        self.assertIs(result["full_candidate_identity_bound"], True)
        self.assertIs(result["candidate_verified_before_and_after_gui"], True)
        self.assertEqual(result["source_git_sha"], SOURCE)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(inspect.call_count, 2, "v2 must verify before and after the GUI")

    def test_identity_change_between_the_two_checks_blocks(self):
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=self.archive, expected=self.digest,
                        static=[{"zip_sha256": self.digest, "source_git_sha": SOURCE},
                                {"zip_sha256": digest_of(b"swapped"), "source_git_sha": SOURCE}])
        self.assertIn("changed between the two GUI checks", str(caught.exception))

    def test_source_change_between_the_two_checks_blocks(self):
        with self.assertRaises(PayloadError) as caught:
            self.accept(archive=self.archive, expected=self.digest,
                        static=[{"zip_sha256": self.digest, "source_git_sha": SOURCE},
                                {"zip_sha256": self.digest, "source_git_sha": "b" * 40}])
        self.assertIn("source identity changed", str(caught.exception))

    # -- CLI surface stays honest ----------------------------------------
    def test_cli_help_advertises_the_pair(self):
        with mock.patch.object(gui, "inspect_rebuilt"), mock.patch.object(gui, "run_gui"):
            with self.assertRaises(SystemExit):
                with mock.patch("sys.argv", ["gui", "--help"]):
                    gui.main()
        text = (Path(gui.__file__).read_text(encoding="utf-8"))
        self.assertIn("--expected-zip-sha256", text)
        self.assertIn("srw.rebuilt-native-gui-acceptance.v2", text)


if __name__ == "__main__":
    unittest.main()
