"""Interactive WPF/WebView2 Windows GUI smoke with a disposable SRW workspace.

The application payload is strictly audited BEFORE launch. No user workspace,
resume, provider credential, or pre-existing database may be passed in. A
successful report establishes GUI LOAD + clean shutdown only, NOT full hiring,
OCR/ASR/AI, backup/restore, or RC acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

if __package__ in ("", None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.native_payload import PayloadError
from scripts.verify_rebuilt_native import inspect_rebuilt

REQUIRED = ("host_started", "backend_ready", "webview_initialized",
            "frontend_loaded", "shutdown_requested", "backend_stopped",
            "workspace_released", "host_closed")
MAX_LOG_SIZE = 10_000_000


def safe_host_events(path: Path, *, offset: int = 0) -> list[str]:
    """Read only recognized event *names*; do not copy raw log lines or IDs."""
    if not path.is_file() or path.is_symlink():
        return []
    size = path.stat().st_size
    if size < offset:
        raise PayloadError("WPF Host log truncated between launch cycles")
    if size - offset > MAX_LOG_SIZE:
        raise PayloadError("WPF Host log exceeded safe parse size")
    with path.open("rb") as stream:
        stream.seek(offset)
        # The Host may still be appending a multibyte JSONL line; incomplete
        # UTF-8 is ignored until a later poll, never mistaken for GUI failure.
        lines = stream.read(MAX_LOG_SIZE + 1).decode("utf-8-sig", errors="replace").splitlines()
    events = []
    for line in lines:
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        event = record.get("event") if isinstance(record, dict) else None
        if event in REQUIRED:
            events.append(event)
    return events


def verify_gui_event_sequence(events: list[str], *, lock_exists: bool) -> dict:
    """Do not mistake HTTP ready for WPF frontend navigation or clean shutdown."""
    if any(event not in events for event in REQUIRED):
        missing = [event for event in REQUIRED if event not in events]
        raise PayloadError("actual Windows WPF event sequence incomplete: " + ", ".join(missing))
    last = -1
    for event in REQUIRED:
        idx = events.index(event, last + 1) if event in events[last + 1:] else -1
        if idx < 0:
            raise PayloadError("actual WPF lifecycle events were out of order: " + event)
        last = idx
    if lock_exists:
        raise PayloadError("candidate GUI closed but temporary workspace lock remains")
    return {"wpf_navigation_loaded": True, "graceful_shutdown": True,
            "workspace_lock_released": True, "observed_events": list(REQUIRED)}


def run_gui(root: Path, *, timeout_seconds: int = 180, cycles: int = 1) -> list[dict]:
    if os.name != "nt":
        raise PayloadError("interactive WPF smoke requires a real Windows desktop session")
    if not 30 <= timeout_seconds <= 1800 or not 1 <= cycles <= 3:
        raise PayloadError("WPF smoke timeout/cycle bounds invalid")
    executable = root / "windows-host" / "SmartRecruitmentWorkbench.exe"
    if executable.is_symlink() or not executable.is_file():
        raise PayloadError("reviewed WPF executable missing")
    results = []
    with tempfile.TemporaryDirectory(prefix="srw-c11-wpf-gui-acceptance-") as directory:
        data = Path(directory) / "data"
        for index in range(cycles):
            log = data / "logs" / "host.log"
            baseline = log.stat().st_size if log.exists() else 0
            print(f"[SRW GUI] Cycle {index + 1}/{cycles}: opening REAL WPF with disposable synthetic workspace.", flush=True)
            process = subprocess.Popen(
                [str(executable), "--application-root", str(root), "--data-root", str(data)],
                cwd=root, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            start = time.monotonic()
            saw_frontend = False
            timed_out = False
            try:
                while time.monotonic() - start < timeout_seconds:
                    if process.poll() is not None:
                        break
                    events = safe_host_events(log, offset=baseline)
                    if "frontend_loaded" in events and not saw_frontend:
                        saw_frontend = True
                        print("[SRW GUI] WebView2 loaded. Inspect UI, then CLOSE WPF normally with X.", flush=True)
                    time.sleep(0.25)
                if process.poll() is None:
                    timed_out = True
                    raise PayloadError("GUI smoke timed out: close WPF normally before deadline")
                events = safe_host_events(log, offset=baseline)
                report = verify_gui_event_sequence(events, lock_exists=(data / "app.lock").exists())
                report["cycle"] = index + 1
                report["normal_process_exit"] = process.returncode == 0
                if process.returncode != 0:
                    raise PayloadError("WPF process exited with nonzero status")
                results.append(report)
                print("[SRW GUI] WPF frontend and clean shutdown verified.", flush=True)
            finally:
                # Never leave an owned temporary backend/window running. A
                # timeout is BLOCKED, not a successful graceful-shutdown test.
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                if timed_out:
                    print("[SRW GUI] Forced exit on timeout; NO graceful shutdown acceptance.", flush=True)
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--cycles", type=int, default=1)
    args = p.parse_args()
    try:
        if os.name != "nt":
            raise PayloadError("interactive WPF GUI acceptance requires Windows")
        if not 30 <= args.timeout <= 1800 or not 1 <= args.cycles <= 3:
            raise PayloadError("WPF smoke bounds invalid")
        root_was_symlink = args.root.is_symlink()
        root = args.root.resolve(strict=True)
        evidence = args.evidence.resolve()
        if root_was_symlink or evidence.is_relative_to(root) or evidence.exists() or evidence.is_symlink():
            raise PayloadError("invalid source candidate or existing/inside evidence destination")
        static = inspect_rebuilt(root)
        cycles = run_gui(root, timeout_seconds=args.timeout, cycles=args.cycles)
        result = {"schema": "srw.rebuilt-native-gui-acceptance.v1",
                  "status": "WPF_GUI_FIRST_USE_SMOKE_PASS_FULL_BUSINESS_PENDING",
                  "source_git_sha": static["source_git_sha"],
                  "static_source_rebuild_passed": True,
                  "actual_native_gui_accepted_for_basic_smoke": True,
                  "full_business_accepted": False,
                  "ocr_asr_ai_accepted": False,
                  "cycles": cycles}
        evidence.parent.mkdir(parents=True, exist_ok=True)
        with evidence.open("x", encoding="utf-8") as out:
            json.dump(result, out, ensure_ascii=False, indent=2, sort_keys=True)
            out.write("\n")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (PayloadError, OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "wpf_gui_accepted": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
