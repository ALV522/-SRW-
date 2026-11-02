"""No-network, no-real-data regressions for the local Core + Browser launcher."""
from __future__ import annotations

import io
import sqlite3
from contextlib import closing
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.start_local_web import (
    EXIT_NO_TRUSTED_CONSOLE,
    UntrustedConsole,
    announce_pairing_code,
    pairing_console_is_trusted,
    production_knowledge_errors,
    workspace_errors,
)

ROOT = Path(__file__).resolve().parents[1]


class _TtyBuffer(io.StringIO):
    """A console stand-in that answers ``isatty()`` the way a real one does."""

    def isatty(self) -> bool:  # pragma: no cover - trivial
        return True


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


class LocalWebPairingConsoleTests(unittest.TestCase):
    """#43 M3A: the pairing code appears once, on the console, and nowhere else.

    It is the one credential a human hands to the browser, so a URL, a query
    string or a repeated log line would leak it outside the trusted channel.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-local-web-pairing-",
                                               ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self._saved = {name: os.environ.get(name) for name in
                       ("RECRUITMENT_SESSION_ENFORCE", "SRW_SYNTHETIC_BROWSER_ACCEPTANCE")}
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _run(self, *, enforce: bool, console=None) -> str:
        import contextlib
        from unittest.mock import patch

        from scripts import start_local_web

        if enforce:
            os.environ["RECRUITMENT_SESSION_ENFORCE"] = "1"
        else:
            os.environ.pop("RECRUITMENT_SESSION_ENFORCE", None)
        os.environ["SRW_SYNTHETIC_BROWSER_ACCEPTANCE"] = "1"
        argv = ["--workspace", str(self.workspace), "--synthetic",
                "--no-browser", "--port", "8799"]
        buffer = console if console is not None else io.StringIO()
        # uvicorn.Server.run blocks forever; the entry point is what matters here.
        with patch("uvicorn.Server.run", return_value=None), contextlib.redirect_stdout(buffer):
            code = start_local_web.main(argv)
        self.assertEqual(code, 0, buffer.getvalue())
        return buffer.getvalue()

    def test_pairing_code_is_printed_once_and_never_in_the_url(self):
        from srw.runtime.business_session_gateway import PAIRING_TTL_SECONDS

        output = self._run(enforce=True, console=_TtyBuffer())
        self.assertIn("PAIRING CODE", output)
        line = next(l for l in output.splitlines() if "PAIRING CODE" in l)
        self.assertIn(str(int(PAIRING_TTL_SECONDS)), line)
        code = line.rsplit(":", 1)[1].strip()
        self.assertGreaterEqual(len(code), 24)
        self.assertEqual(output.count(code), 1, "the code must not be repeated elsewhere")
        url_line = next(l for l in output.splitlines() if "http://127.0.0.1" in l)
        self.assertNotIn("?", url_line)
        self.assertNotIn(code, url_line)

    def test_default_off_prints_no_pairing_code(self):
        output = self._run(enforce=False, console=io.StringIO())
        self.assertNotIn("PAIRING CODE", output)
        self.assertIn("http://127.0.0.1:8799/v1", output)


class PairingConsoleTrustTests(unittest.TestCase):
    """R1: the code only ever reaches a console a human is looking at."""

    def test_a_pipe_and_an_in_memory_buffer_are_not_trusted(self):
        self.assertFalse(pairing_console_is_trusted(io.StringIO()))
        read_fd, write_fd = os.pipe()
        try:
            with os.fdopen(write_fd, "w") as pipe:
                self.assertFalse(pairing_console_is_trusted(pipe),
                                 "a redirected stdout is a log sink, not a console")
        finally:
            os.close(read_fd)

    def test_a_real_terminal_device_is_trusted(self):
        try:
            import pty
        except ImportError:  # Windows has no pty module; the OS answer is untestable here
            self.skipTest("pty module unavailable on this platform")
        master, slave = pty.openpty()
        try:
            with os.fdopen(slave, "w") as console:
                self.assertTrue(pairing_console_is_trusted(console))
        finally:
            os.close(master)

    def test_announce_mints_nothing_when_the_stream_is_not_a_console(self):
        from srw.runtime.business_session_gateway import BusinessSessionGateway

        gateway = BusinessSessionGateway()
        buffer = io.StringIO()
        with self.assertRaises(UntrustedConsole):
            announce_pairing_code(gateway, buffer)
        self.assertEqual(buffer.getvalue(), "", "nothing may be written to a log sink")
        self.assertFalse(gateway.has_pairing_code, "a refused delivery must not mint a code")

    def test_announce_writes_one_usable_code_to_a_console(self):
        from srw.runtime.business_session_gateway import BusinessSessionGateway

        gateway = BusinessSessionGateway()
        console = _TtyBuffer()
        code = announce_pairing_code(gateway, console)
        self.assertIn(code, console.getvalue())
        self.assertEqual(console.getvalue().count(code), 1)
        token, csrf = gateway.pair(code)  # the printed code really is the live one
        self.assertTrue(token.startswith("srw1."))
        self.assertTrue(csrf)


class RedirectedLauncherTests(unittest.TestCase):
    """A real subprocess with a real pipe: the fail-closed branch end to end."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="srw-local-web-redirected-")
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name) / "workspace"

    def test_redirected_stdout_refuses_to_start_and_creates_nothing(self):
        env = dict(os.environ)
        env.update({"RECRUITMENT_SESSION_ENFORCE": "1",
                    "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
                    "PYTHONIOENCODING": "utf-8"})
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "start_local_web.py"),
             "--workspace", str(self.workspace), "--synthetic",
             "--no-browser", "--port", "8799"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=45,
        )
        combined = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, EXIT_NO_TRUSTED_CONSOLE, combined)
        self.assertEqual(completed.stdout, "", "the log sink must stay completely empty")
        self.assertNotIn("PAIRING CODE", combined)
        self.assertNotIn("single use", combined)
        self.assertIn("interactive terminal", completed.stderr)
        self.assertFalse(self.workspace.exists(),
                         "a refused start must not create a workspace, lock or database")

    def test_invalid_flag_still_reports_the_configuration_error(self):
        env = dict(os.environ)
        env.update({"RECRUITMENT_SESSION_ENFORCE": "yes",
                    "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
                    "PYTHONIOENCODING": "utf-8"})
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "start_local_web.py"),
             "--workspace", str(self.workspace), "--synthetic",
             "--no-browser", "--port", "8799"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=45,
        )
        combined = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, EXIT_NO_TRUSTED_CONSOLE, combined)
        self.assertIn("RECRUITMENT_SESSION_ENFORCE", combined)
        self.assertNotIn("PAIRING CODE", combined)


if __name__ == "__main__":
    unittest.main()
