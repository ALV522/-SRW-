"""Synthetic tests for the index-aware manifest updater (#166).

Everything runs in a throwaway Git repository: no project source, no production
archive, no network. The point is to pin three properties that the previous
`--write` implementation could not give us:

* the digest describes the **committed blob**, not a platform-dependent checkout;
* the manifest is written as LF bytes on Windows too;
* `--paths` changes only the named lines and refuses to hide drift elsewhere.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.refresh_source_manifest import (
    CURRENT,
    RefreshError,
    main,
    parse_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRITY_SCRIPT = REPO_ROOT / "scripts" / "check_source_integrity.py"


class ManifestWorkbench(unittest.TestCase):
    """A tiny real Git repository; `git` is the authority exactly as in production."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="srw-manifest-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "scripts").mkdir()
        shutil.copy(INTEGRITY_SCRIPT, self.root / "scripts" / "check_source_integrity.py")
        (self.root / "SOURCE_RECOVERY_MANIFEST.sha256").write_bytes(b"")
        # Same rule as the real repository: byte-code caches are never tracked.
        self.write(".gitignore", b"__pycache__/\n*.py[cod]\n")
        (self.root / "docs").mkdir()
        self.write("a.py", b"print('a')\n")
        self.write("b.py", b"print('b')\n")
        self.write("docs/c.md", b"# c\n")
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "fixture")
        self.git("config", "core.autocrlf", "false")
        self.commit("initial")

    # -- helpers ---------------------------------------------------------
    def write(self, relative: str, data: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                              text=True, check=True).stdout

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def stage(self, relative: str) -> None:
        self.git("add", "--", relative)

    def manifest_bytes(self) -> bytes:
        return (self.root / CURRENT).read_bytes()

    def manifest(self) -> dict[str, str]:
        return parse_manifest(self.manifest_bytes().decode("utf-8"))

    def blob_bytes(self, relative: str) -> bytes:
        return subprocess.run(["git", "cat-file", "blob", f":{relative}"], cwd=self.root,
                              capture_output=True, check=True).stdout

    def run_main(self, *args: str) -> int:
        return main(list(args), root=self.root)

    def build(self) -> None:
        self.assertEqual(self.run_main("--write"), 0)


class FullRenderTests(ManifestWorkbench):
    def test_full_write_is_lf_and_covers_every_tracked_file(self) -> None:
        self.build()
        raw = self.manifest_bytes()
        self.assertNotIn(b"\r\n", raw)
        entries = parse_manifest(raw.decode("utf-8"))
        self.assertEqual(sorted(entries), [".gitignore", "SOURCE_RECOVERY_MANIFEST.sha256",
                                           "a.py", "b.py", "docs/c.md",
                                           "scripts/check_source_integrity.py"])
        self.assertNotIn(CURRENT, entries, "the manifest never pins itself")
        for path, digest in entries.items():
            self.assertEqual(digest, hashlib.sha256(self.blob_bytes(path)).hexdigest(), path)

    def test_stdout_mode_writes_nothing(self) -> None:
        self.build()
        before = self.manifest_bytes()
        self.write("a.py", b"print('changed')\n")
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.manifest_bytes(), before,
                         "read-only mode must not touch the manifest")


class IncrementalTests(ManifestWorkbench):
    def test_paths_updates_only_the_selected_line(self) -> None:
        self.build()
        before = self.manifest_bytes().decode("utf-8").splitlines()
        self.write("b.py", b"print('b2')\n")
        self.commit("change b")
        self.assertEqual(self.run_main("--write", "--paths", "b.py"), 0)
        after = self.manifest_bytes().decode("utf-8").splitlines()
        self.assertEqual(len(before), len(after))
        changed = [(x, y) for x, y in zip(before, after) if x != y]
        self.assertEqual(len(changed), 1, changed)
        self.assertTrue(changed[0][1].endswith("  b.py"))
        self.assertEqual(self.manifest()["b.py"],
                         hashlib.sha256(self.blob_bytes("b.py")).hexdigest())

    def test_paths_inserts_a_new_tracked_file_once_in_sorted_order(self) -> None:
        self.build()
        self.write("convergence_tests/new_test.py", b"# new\n")
        self.commit("add new")
        self.assertEqual(self.run_main("--write", "--paths", "convergence_tests/new_test.py"), 0)
        lines = self.manifest_bytes().decode("utf-8").splitlines()
        paths = [line.split("  ", 1)[1] for line in lines]
        self.assertEqual(paths.count("convergence_tests/new_test.py"), 1)
        self.assertEqual(paths, sorted(paths))

    def test_disjoint_incremental_updates_compose_to_the_full_render(self) -> None:
        self.build()
        # Two PR-like changes, each touching exactly one file on top of a synced
        # manifest: the second update must not need the first file re-selected.
        self.write("a.py", b"print('a2')\n")
        self.commit("touch a")
        self.assertEqual(self.run_main("--write", "--paths", "a.py"), 0)
        self.write("docs/c.md", b"# c2\n")
        self.commit("touch c")
        self.assertEqual(self.run_main("--write", "--paths", "docs/c.md"), 0)
        incremental = self.manifest_bytes().decode("utf-8")
        self.build()
        self.assertEqual(self.manifest_bytes().decode("utf-8"), incremental,
                         "incremental writes must equal a full render")


class RefusalTests(ManifestWorkbench):
    def assert_refused(self, *args: str, expect: str | None = None) -> None:
        """A refusal must exit 2, leave the manifest alone and name its reason."""
        before = self.manifest_bytes()
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            code = self.run_main(*args)
        self.assertEqual(code, 2)
        self.assertEqual(self.manifest_bytes(), before, "a refusal must not write")
        if expect is not None:
            self.assertIn(expect, captured.getvalue(),
                          f"refusal must explain itself, got: {captured.getvalue()!r}")

    def test_untracked_path_is_refused(self) -> None:
        self.build()
        self.write("untracked.py", b"# not in the index\n")
        self.assert_refused("--write", "--paths", "untracked.py", expect="not tracked")

    def test_unsafe_selection_forms_are_refused(self) -> None:
        self.build()
        for bad in ("", "/etc/passwd", "C:/tmp/x", "a\\b.py", "../a.py",
                    "./a.py", "docs//c.md"):
            with self.subTest(path=bad):
                self.assert_refused("--write", "--paths", bad)

    def test_duplicate_and_alias_selections_are_refused(self) -> None:
        self.build()
        for bad in ("a.py,a.py", "a.py,A.PY"):
            with self.subTest(paths=bad):
                self.assert_refused("--write", "--paths", bad, expect="ambiguous alias")

    def test_non_nfc_selection_is_refused(self) -> None:
        self.build()
        decomposed = "cafe\u0301.py"  # NFD
        # The refusal must come from the NFC rule, not from "not tracked":
        # otherwise removing the rule would be invisible to this test.
        self.assert_refused("--write", "--paths", decomposed, expect="NFC")

    def test_unselected_drift_fails_closed(self) -> None:
        self.build()
        self.write("a.py", b"print('a2')\n")
        self.commit("drift in a")
        # b.py is selected; a.py drifted. The refusal must name the drift, not
        # merely fail later inside the post-write integrity check.
        self.assert_refused("--write", "--paths", "b.py", expect="not in --paths")

    def test_removal_is_refused_by_paths_and_by_write(self) -> None:
        self.build()
        self.git("rm", "-q", "--", "b.py")
        self.commit("delete b")
        self.assert_refused("--write", "--paths", "a.py", expect="no longer tracked")
        self.assert_refused("--write", expect="allow-removals")
        self.assertEqual(self.run_main("--write", "--allow-removals"), 0)
        self.assertNotIn("b.py", self.manifest())

    def test_malformed_manifest_is_refused(self) -> None:
        self.build()
        self.write(CURRENT, b"not-a-digest  a.py\n")
        self.assert_refused("--write", expect="64-hex")
        self.assert_refused("--write", "--paths", "a.py", expect="64-hex")

    def test_failed_integrity_after_write_restores_previous_bytes(self) -> None:
        self.build()
        before = self.manifest_bytes()
        # Divergent working tree: the manifest is rendered from the index, but the
        # full check reads the working tree and must refuse to leave it written.
        self.write("a.py", b"print('divergent')\n")
        self.assertEqual(self.run_main("--write"), 2)
        self.assertEqual(self.manifest_bytes(), before)

    def test_allow_removals_is_rejected_with_paths(self) -> None:
        self.build()
        self.assert_refused("--write", "--paths", "a.py", "--allow-removals",
                            expect="only applies to --write")


class CrlfProvenanceTests(ManifestWorkbench):
    def make_crlf_checkout(self) -> str:
        """Index holds LF, working tree holds CRLF: the Windows trap."""
        self.build()
        lf = self.blob_bytes("a.py")
        self.assertNotIn(b"\r\n", lf)
        self.write("a.py", lf.replace(b"\n", b"\r\n"))
        return hashlib.sha256(lf).hexdigest()

    def test_crlf_checkout_is_refused_without_from_index(self) -> None:
        index_digest = self.make_crlf_checkout()
        before = self.manifest_bytes()
        self.assertEqual(self.run_main("--write", "--paths", "a.py"), 2)
        self.assertEqual(self.manifest_bytes(), before,
                         "the refusal must leave the previous (index-correct) digest alone")
        self.assertEqual(self.manifest()["a.py"], index_digest)

    def test_from_index_pins_the_committed_blob_not_the_checkout(self) -> None:
        index_digest = self.make_crlf_checkout()
        self.assertEqual(self.run_main("--write", "--paths", "a.py", "--from-index"), 0)
        self.assertEqual(self.manifest()["a.py"], index_digest,
                         "the digest must equal `git cat-file blob :a.py`")
        self.assertIn(b"\r\n", (self.root / "a.py").read_bytes(),
                      "the divergent checkout must be left untouched")
        self.assertNotIn(b"\r\n", self.manifest_bytes())

    def test_full_write_from_index_ignores_crlf_checkout(self) -> None:
        index_digest = self.make_crlf_checkout()
        # Full mode hashes the index; the post-write check reads the checkout, so
        # this legitimately fails closed and restores. That is the loud signal.
        before = self.manifest_bytes()
        self.assertEqual(self.run_main("--write"), 2)
        self.assertEqual(self.manifest_bytes(), before,
                         "restored bytes must still pin the index blob")
        self.assertEqual(self.manifest()["a.py"], index_digest)


class ErrorTypeTests(unittest.TestCase):
    def test_refresh_error_is_not_a_silent_value_error(self) -> None:
        self.assertTrue(issubclass(RefreshError, Exception))
        self.assertFalse(issubclass(RefreshError, ValueError),
                         "a refusal must not be swallowed by generic ValueError handlers")


if __name__ == "__main__":
    unittest.main()
