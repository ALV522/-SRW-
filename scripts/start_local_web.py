"""Source-development Local Web entry to the REAL SRW C11 Core.

This is NOT a distributable Web/Native Portable, a SaaS server or a shared
WPF/Core supervisor. It never uses production data without an explicit path.
Use --synthetic only for isolated CI/browser acceptance.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
import sqlite3
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "backend"), str(ROOT / "convergence_tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

CURRENT_SCHEMA = json.loads((ROOT / "VERSION_POLICY.json").read_text(encoding="utf-8"))["schema_revision"]
KNOWLEDGE_NAMES = ("taxonomy", "job_info", "competency", "market_reference", "reference")


def workspace_errors(path: Path, *, reuse: bool, synthetic: bool,
                     source_root: Path = ROOT) -> list[str]:
    """Pure validation; no filesystem mutation or database opening."""
    problems: list[str] = []
    if not path.is_absolute():
        problems.append("workspace must be an explicit absolute path")
        return problems
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        problems.append("workspace must be a real directory, not a symlink or file")
        return problems
    candidate = path.resolve()
    root = source_root.resolve()
    if candidate == root or candidate.is_relative_to(root) or root.is_relative_to(candidate):
        problems.append("workspace must be separate from source/application directory")
    if (candidate / "data").is_symlink() or (candidate / "data" / "srw_v1.db").is_symlink():
        problems.append("workspace data/database must not be symbolic links")
    # Read-only lease inspection: a live/foreign/corrupt lease blocks, a lease
    # whose owning process is gone is left for WorkspaceLease.acquire() to
    # recover atomically. Validation must not delete another carrier's lease.
    from srw.workspace_lease import inspect_lease

    lease = inspect_lease(candidate / "data")
    if lease.state in ("active", "foreign", "corrupt"):
        owner = lease.holder.describe() if lease.holder is not None else lease.detail
        problems.append(f"app.lock already owned: {owner}")
    if (candidate / "data" / ".srw-instance.lock").is_symlink():
        problems.append("workspace lock is a symlink")
    if candidate.exists():
        children = list(candidate.iterdir())
        if synthetic and children:
            problems.append("synthetic workspace must be empty")
        if not synthetic and not reuse and children:
            problems.append("existing workspace requires --reuse-workspace")
        if not synthetic and reuse:
            db = candidate / "data" / "srw_v1.db"
            if not db.is_file() or db.is_symlink():
                problems.append("--reuse-workspace requires an existing non-symlink SRW database")
            else:
                try:
                    with db.open("rb") as stream:
                        if stream.read(16) != b"SQLite format 3" + bytes([0]):
                            raise ValueError("invalid SQLite header")
                    # Open read-only. Never create or migrate a database just
                    # to decide whether it is safe to reuse.
                    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as connection:
                        result = connection.execute("PRAGMA quick_check").fetchone()
                        revision = connection.execute(
                            "SELECT schema_revision FROM v1_schema_meta LIMIT 1"
                        ).fetchone()
                    if result != ("ok",) or not revision or revision[0] != CURRENT_SCHEMA:
                        raise ValueError("SQLite integrity/schema mismatch")
                except (OSError, sqlite3.Error, ValueError) as exc:
                    problems.append(f"existing SRW workspace integrity/schema rejected: {exc}")
    elif reuse:
        problems.append("--reuse-workspace cannot create a missing workspace")
    if reuse and synthetic:
        problems.append("synthetic mode never reuses existing workspaces")
    return problems


def production_knowledge_errors(root: Path) -> list[str]:
    errors: list[str] = []
    if root.is_symlink() or not root.is_dir():
        return ["production Knowledge path is missing or symlinked"]
    for name in KNOWLEDGE_NAMES:
        path = root / name / "knowledge.db"
        if path.is_symlink() or not path.is_file():
            errors.append(f"Knowledge database missing: {name}")
            continue
        with path.open("rb") as stream:
            if stream.read(16) != b"SQLite format 3" + bytes([0]):
                errors.append(f"Knowledge database invalid SQLite header: {name}")
    return errors


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SRW real C11 Core + local Browser (source preview only)")
    p.add_argument("--workspace", type=Path, required=True,
                   help="explicit separate workspace; NEVER point to active Windows or personal data")
    p.add_argument("--knowledge-root", type=Path, default=ROOT / "knowledge" / "active")
    p.add_argument("--reuse-workspace", action="store_true",
                   help="explicitly reopen a previously created and inactive SRW web workspace")
    p.add_argument("--synthetic", action="store_true",
                   help="isolated testing only; requires SRW_SYNTHETIC_BROWSER_ACCEPTANCE=1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--supervisor", action="store_true",
                   help="ADR-0003 S1: attach to (or derive) a detached Core Supervisor instead of "
                        "running the Core in this process. Default off = today's behaviour verbatim.")
    p.add_argument("--supervisor-idle-grace", type=float, default=300.0,
                   help="idle seconds a derived Supervisor waits after the last carrier detaches")
    return p


def _open_when_ready(port: int) -> None:
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=0.4) as response:
                if response.status == 200:
                    webbrowser.open(f"http://127.0.0.1:{port}/v1")
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.15)


def _run_with_supervisor(args: argparse.Namespace, *, data: Path, db: Path, frontend: Path, knowledge: Path) -> int:
    """ADR-0003 S1 carrier path: never hold the lease; attach to the Core Supervisor."""
    from urllib.parse import urlparse

    from srw.supervisor.client import SupervisorUnavailable, ensure_supervisor

    try:
        handle = ensure_supervisor(
            args.workspace.expanduser(),
            carrier="local-web",
            edition="local-web",
            database=db,
            frontend_dist=frontend,
            knowledge_root=knowledge,
            idle_grace_seconds=args.supervisor_idle_grace,
        )
    except SupervisorUnavailable as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    port = urlparse(handle.base_url).port or args.port
    print(f"SRW C11 Local Web (Supervisor mode, instance {handle.instance_id[:8]}): http://127.0.0.1:{port}/v1", flush=True)
    print("This carrier holds no workspace lease; the Core survives this carrier closing.", flush=True)
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    try:
        while True:
            handle.heartbeat()
            time.sleep(30)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            handle.detach()
        except SupervisorUnavailable:
            pass
    return 0


def run(args: argparse.Namespace) -> int:
    workspace = args.workspace.expanduser()
    errors = workspace_errors(workspace, reuse=args.reuse_workspace, synthetic=args.synthetic)
    if args.synthetic and os.environ.get("SRW_SYNTHETIC_BROWSER_ACCEPTANCE") != "1":
        errors.append("synthetic mode requires explicit SRW_SYNTHETIC_BROWSER_ACCEPTANCE=1")
    if not 1024 <= args.port <= 65535:
        errors.append("port must be 1024..65535")
    frontend = ROOT / "frontend" / "dist"
    if not (frontend / "index.html").is_file():
        errors.append("real SRW frontend/dist/index.html missing")
    knowledge = args.knowledge_root.expanduser().resolve()
    if not args.synthetic:
        if (knowledge / "active").is_dir():
            knowledge = knowledge / "active"
        errors.extend(production_knowledge_errors(knowledge))
    if errors:
        for problem in errors:
            print(f"BLOCKED: {problem}", file=sys.stderr)
        return 2

    # All validation above is read-only. Synthetic fixtures are never confused
    # with production Knowledge; mode must be explicitly selected.
    workspace.mkdir(parents=True, exist_ok=True)
    if args.synthetic:
        from knowledge_fixture import create_minimal_knowledge_tree
        knowledge = create_minimal_knowledge_tree(workspace / "knowledge" / "active")
    data = workspace / "data"
    data.mkdir(exist_ok=True)
    db = data / "srw_v1.db"
    if args.supervisor:
        return _run_with_supervisor(args, data=data, db=db, frontend=frontend, knowledge=knowledge)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    try:
        release_id = json.loads((ROOT / "BUILD_INFO.json").read_text(encoding="utf-8")).get("release_id", version)
    except (OSError, ValueError):
        release_id = version

    from scripts import launch_alpha10
    from srw.api.app import create_v1_app
    from srw.workspace_lease import WorkspaceLease, WorkspaceLeaseError
    import uvicorn

    # Two locks, in a fixed order, and both are needed:
    #  1. .srw-instance.lock keeps older alpha10 Portables (which only know that
    #     file) from attaching to the same data directory.
    #  2. data/app.lock is the cross-carrier lease shared with the WPF Host. It is
    #     created atomically, so a Host starting while this Core runs now fails
    #     instead of taking a second write handle on the same SQLite database.
    # This is still NOT a Core supervisor: whichever carrier acquires app.lock
    # owns the Core, and the two entry points stay independent processes.
    with launch_alpha10.InstanceLock(data / ".srw-instance.lock"):
        try:
            lease = WorkspaceLease(
                data, edition="local-web", port=args.port,
                version=version, release_id=release_id,
            ).acquire()
        except WorkspaceLeaseError as exc:
            print(f"BLOCKED: {exc}", file=sys.stderr)
            return 2
        with lease:
            if not args.synthetic:
                launch_alpha10.DATA, launch_alpha10.DB = data, db
                launch_alpha10.apply_pending_restore()
            os.environ["RECRUITMENT_EDITION"] = "web"
            os.environ["RECRUITMENT_RUNTIME_MODE"] = "browser"
            os.environ["SRW_BACKGROUND_WORKER"] = "0" if args.synthetic else "1"
            app = create_v1_app(
                f"sqlite+pysqlite:///{db.as_posix()}",
                data_dir=data, knowledge_dir=knowledge, frontend_dist=frontend,
            )
            config = uvicorn.Config(
                app, host="127.0.0.1", port=args.port,
                log_level="warning" if args.synthetic else "info", access_log=False,
            )
            server = uvicorn.Server(config)
            app.state.shutdown_callback = lambda: setattr(server, "should_exit", True)
            print(f"SRW C11 Local Web SOURCE PREVIEW: http://127.0.0.1:{args.port}/v1", flush=True)
            print("This is one real Core and one local Browser. NOT a dual-carrier GA/RC.", flush=True)
            if not args.no_browser:
                threading.Thread(target=_open_when_ready, args=(args.port,), daemon=True).start()
            server.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
