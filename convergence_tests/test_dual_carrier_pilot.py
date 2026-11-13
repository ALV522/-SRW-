"""Static safety contract for the two Q1R10 pilot launchers.

This does not pretend to execute cmd.exe, Windows WPF or a production Web
Core on Linux. B/C must still perform the exact-artifact Windows E2E.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DualCarrierPilotLaunchers(unittest.TestCase):
    def test_exe_uses_host_and_explicit_private_data_root(self):
        script = (ROOT / "START-SRW-EXE.cmd").read_text(encoding="utf-8")
        self.assertIn("windows-host\\SmartRecruitmentWorkbench.exe", script)
        # %~dp0 ends with backslash; a quote after it is parsed as escaped.
        # Only the outbound argument is stripped, not APPROOT file joins.
        self.assertIn('set "APPROOT_ARG=%APPROOT%"', script)
        self.assertIn('APPROOT_ARG:~-1%', script)
        self.assertIn('APPROOT_ARG:~0,-1%', script)
        self.assertIn('--application-root "%APPROOT_ARG%"', script)
        self.assertNotIn('--application-root "%APPROOT%"', script)
        self.assertIn('--data-root "%DATA%"', script)
        self.assertIn("%LOCALAPPDATA%\\SRW\\DualCarrierV0", script)
        self.assertNotIn("taskkill", script.lower())
        self.assertNotIn("rmdir", script.lower())

    def test_web_uses_real_core_pinned_runtime_and_session_on(self):
        script = (ROOT / "START-SRW-WEB.cmd").read_text(encoding="utf-8")
        self.assertIn("runtime\\python.exe", script)
        self.assertIn("scripts\\start_local_web.py", script)
        self.assertIn("set \"RECRUITMENT_SESSION_ENFORCE=1\"", script)
        self.assertIn('"%PYTHON%" -I -B', script)
        self.assertIn('--workspace "%WORKSPACE%"', script)
        self.assertIn('--knowledge-root "%KNOWLEDGE%"', script)
        self.assertIn('--port 8765', script)
        self.assertIn("if exist \"%WORKSPACE%\\data\\srw_v1.db\" set \"REUSE=--reuse-workspace\"", script)
        self.assertNotIn("--synthetic", script)
        self.assertNotIn("SRW_SYNTHETIC_BROWSER_ACCEPTANCE", script)
        self.assertNotIn("0.0.0.0", script)

    def test_both_entry_points_share_only_private_workspace(self):
        exe = (ROOT / "START-SRW-EXE.cmd").read_text(encoding="utf-8")
        web = (ROOT / "START-SRW-WEB.cmd").read_text(encoding="utf-8")
        literal = "%LOCALAPPDATA%\\SRW\\DualCarrierV0"
        self.assertIn(literal, exe)
        self.assertIn(literal, web)
        for script in (exe, web):
            for risky in ("del /", "rmdir", "robocopy", "format ", "rd /s", "powershell -encodedcommand"):
                self.assertNotIn(risky, script.lower())


if __name__ == "__main__":
    unittest.main()
