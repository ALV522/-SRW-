"""Read-only Windows Native Host log acceptance, without disclosing local identifiers.

A valid GUI baseline requires one coherent Host session: Windows backend ready,
WebView2 initialized/frontend loaded, and orderly backend/workspace shutdown.
Actual recruiting operations are reported independently from GUI acceptance.
Never claim complete business, Provider, OCR/ASR or persistence acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import re
from pathlib import Path

REQUIRED = ("host_started", "paths_resolved", "workspace_lock_acquired",
            "backend_process_started", "backend_ready", "webview_initialized",
            "frontend_loaded", "shutdown_requested", "backend_stopped",
            "workspace_released", "host_closed")
FATAL = {"webview_failed", "backend_start_non_retryable", "backend_force_kill",
         "backend_start_retry", "shutdown_request_failed", "backend_exception"}
HTTP = re.compile(r'"(GET|POST|PATCH|PUT|DELETE) (/[^ ]+) HTTP/1\.[01]" (\d{3})')
RELEASE_EVENTS = ("frontend_loaded", "host_closed")
# Host versions since the privacy-preserving BackendOutputPrivacy classifier
# emit only a route family, method and HTTP status. These labels are stable,
# nonidentifying categories, NOT exact user actions or endpoint identities.
REDACTED_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REDACTED_API_FAMILIES = frozenset({
    "candidate_api", "project_api", "protocol_api", "settings_api",
    "runtime_api", "other_api",
})


def _status(line: str):
    match = HTTP.search(line)
    if match:
        method, uri, code = match.groups()
        return method, uri.split("?")[0], int(code)
    return None


def record_failure(record: dict) -> str | None:
    """Return a fixed diagnostic category, never raw messages or identifiers."""
    event = record.get("event")
    if not isinstance(event, str):
        return "invalid Host event"
    if event in FATAL:
        return "Host failure or forced shutdown"
    details = record.get("details")
    details = details if isinstance(details, dict) else {}
    if event == "backend_http":
        status = details.get("status")
        if type(status) is not int or not 100 <= status <= 599:
            return "invalid structured HTTP status"
        if status >= 500:
            return "HTTP 5xx in Host session"
    if event in {"backend_stdout", "backend_stderr"}:
        line = details.get("line")
        if not isinstance(line, str):
            return "invalid legacy backend output record"
        parsed = _status(line)
        if parsed:
            return "HTTP 5xx in Host session" if parsed[2] >= 500 else None
        if re.search(r"^\s*(?:Traceback\b|ERROR\b|CRITICAL\b|(?:[A-Za-z_][\w.]*\.)?(?:[A-Za-z_][\w]*Error|[A-Za-z_][\w]*Exception|Exception)\s*:)", line):
            return "backend exception or fatal log"
    return None


def inspect(log: Path) -> dict:
    if not log.is_file() or log.is_symlink():
        raise ValueError("Host log missing or symbolic link")
    sessions: dict[str, list[dict]] = {}
    malformed = 0
    for line in log.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(record, dict) or not isinstance(record.get("identity"), dict):
            malformed += 1
            continue
        session = record["identity"].get("host_session_id")
        if not isinstance(session, str) or not session:
            malformed += 1
            continue
        sessions.setdefault(session, []).append(record)
    if not sessions:
        raise ValueError("no parseable Host sessions")

    # Use only the latest startup-ordered session; never stitch together
    # readiness and shutdown events from separate Host launches.
    latest = max(sessions.values(), key=lambda records: records[0].get("ts", ""))
    events = [str(row.get("event", "")) for row in latest]
    missing = [event for event in REQUIRED if event not in events]
    ordered = not missing and all(events.index(a) < events.index(b)
                                  for a, b in zip(REQUIRED, REQUIRED[1:]))
    fatal = sorted(set(events) & FATAL)
    failures: list[str] = []
    issues = set()
    success_requests = Counter()
    # New WPF builds deliberately suppress all original URLs and applicant IDs
    # in Host logs. Never claim a specific business endpoint from a route family.
    # Prefer sanitized records when both old/new formats appear so one action
    # cannot be double-counted across two log transport representations.
    structured_http_present = any(row.get("event") == "backend_http" for row in latest)
    redacted_write_counts = Counter()
    for row in latest:
        failure = record_failure(row)
        if failure:
            failures.append(failure)
            continue
        if row.get("event") == "backend_http":
            details = row.get("details")
            details = details if isinstance(details, dict) else {}
            method = details.get("method")
            route = details.get("route")
            status = details.get("status")
            if (isinstance(method, str) and isinstance(route, str)
                    and method in REDACTED_MUTATION_METHODS
                    and route in REDACTED_API_FAMILIES
                    and type(status) is int and 200 <= status < 300):
                redacted_write_counts[f"{method} {route}"] += 1
            # No raw values, URIs, IDs or unrecognized route labels are emitted.
            continue
        if row.get("event") != "backend_stdout":
            continue
        raw = str((row.get("details") or {}).get("line", ""))
        parsed = _status(raw)
        if parsed is None:
            continue
        method, uri, code = parsed
        if structured_http_present:
            # Old Uvicorn access lines may coexist with the structured event.
            # They are not a second proof of an independent business write.
            continue
        if code >= 500:
            failures.append("HTTP 5xx in Host session")
        elif code == 404 and uri == "/favicon.ico":
            issues.add("favicon_404_nonblocking")
        elif code >= 400:
            issues.add("HTTP_4xx_requires_review")
        elif code < 400:
            if method == "POST" and uri == "/api/v1/projects":
                success_requests["project_created_http_200"] += (code == 200)
            if method == "PATCH" and uri.startswith("/api/v1/protocol-revisions/"):
                success_requests["protocol_revision_updated_http_200"] += (code == 200)
    durations: dict[str, float] = {}
    try:
        start = datetime.fromisoformat(next(x["ts"] for x in latest if x.get("event") == "host_started"))
        for key, event in [("seconds_to_backend_ready", "backend_ready"),
                           ("seconds_to_frontend_loaded", "frontend_loaded"),
                           ("seconds_to_host_closed", "host_closed")]:
            when = datetime.fromisoformat(next(x["ts"] for x in latest if x.get("event") == event))
            durations[key] = round((when - start).total_seconds(), 3)
    except (ValueError, KeyError, StopIteration):
        issues.add("timing_unavailable")

    accepted = ordered and not fatal and not failures and malformed == 0
    return {
        "schema": "srw.native-windows-host-log-acceptance.v1",
        "status": "WINDOWS_GUI_BASELINE_HOST_LOG_PASS" if accepted else "WINDOWS_GUI_HOST_LOG_INCOMPLETE_OR_FAILED",
        "sessions_in_log": len(sessions),
        "events_in_latest_session": len(latest),
        "required_lifecycle_events_complete": ordered,
        "missing_lifecycle_event_names": missing,
        "nonretryable_or_forced_host_events": fatal,
        "fatal_log_count": len(failures),
        "malformed_log_lines": malformed,
        "business_operations_http_success": dict(success_requests),
        "business_http_redacted_write_counts": dict(redacted_write_counts),
        "redacted_http_family_evidence_only": structured_http_present,
        "nonblocking_issues": sorted(issues),
        "timing": durations,
        "wpf_window_and_frontend_loaded": "frontend_loaded" in events,
        "host_shutdown_clean": all(e in events for e in
                                   ("shutdown_requested", "backend_stopped",
                                    "workspace_released", "host_closed")),
        "full_recruitment_business_accepted": False,
        "ocr_asr_ai_provider_accepted": False,
        "backup_restore_accepted": False,
        "user_identifiers_or_local_paths_in_report": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-log", required=True, type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    try:
        report = inspect(args.host_log)
        if args.evidence:
            if args.evidence.exists():
                raise ValueError("refusing to overwrite existing GUI log evidence")
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "WINDOWS_GUI_BASELINE_HOST_LOG_PASS" else 2
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
