from __future__ import annotations

"""Windows Desktop Host compatibility launcher.

This preserves the stable 0.8.x host ABI while running the Convergence backend.
The WPF host owns the workspace lock and provides instance/session identity in env.
"""

import argparse
from contextlib import ExitStack
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for entry in (str(BACKEND), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SRW Windows Desktop backend launcher")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--edition", choices=("web", "windows"), default=os.environ.get("RECRUITMENT_EDITION", "web"))
    p.add_argument("--workspace-lock", choices=("backend", "host"), default="backend")
    return p.parse_args()


def _required_host_identity() -> None:
    missing = [name for name in (
        "RECRUITMENT_INSTANCE_ID", "RECRUITMENT_SESSION_ID", "RECRUITMENT_SESSION_TOKEN"
    ) if not os.environ.get(name, "").strip()]
    if missing:
        raise SystemExit("HOST_WORKSPACE_INVALID: missing " + ", ".join(missing))


def main() -> int:
    args = parse_args()
    if args.workspace_lock == "host":
        if args.edition != "windows":
            raise SystemExit("HOST_WORKSPACE_INVALID: host-owned workspace requires windows edition")
        _required_host_identity()

    data_dir = Path(os.environ.get("RECRUITMENT_DATA_DIR", str(ROOT / "data"))).expanduser().resolve()
    frontend = Path(os.environ.get("RECRUITMENT_FRONTEND_DIST", str(ROOT / "frontend" / "dist"))).expanduser().resolve()
    knowledge = Path(os.environ.get("RECRUITMENT_KNOWLEDGE_DIR", str(ROOT / "knowledge"))).expanduser().resolve()
    if (knowledge / "active").is_dir():
        knowledge = knowledge / "active"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "srw_v1.db"

    # A standalone backend is also a workspace writer. It must not bypass the
    # directory lease shared by the Local Web launcher and WPF Host. Acquire
    # both locks before pending restore or opening SQLite, then hold them until
    # Uvicorn has completely stopped. In --workspace-lock host mode, the WPF
    # process already owns the lease; never try to acquire it a second time.
    with ExitStack() as stack:
        if args.workspace_lock == "backend":
            import launch_alpha10 as portable_launcher
            from srw.workspace_lease import WorkspaceLease, WorkspaceLeaseError

            # Legacy Portables only know the old advisory file lock. Keep the
            # acquisition order identical to scripts/start_local_web.py.
            stack.enter_context(portable_launcher.InstanceLock(data_dir / ".srw-instance.lock"))
            edition = "windows" if args.edition == "windows" else "local-web"
            try:
                stack.enter_context(WorkspaceLease(
                    data_dir, edition=edition, port=args.port,
                    version=(ROOT / "VERSION").read_text(encoding="utf-8").strip(),
                ))
            except WorkspaceLeaseError as exc:
                raise SystemExit(f"BLOCKED: {exc}") from None

        # Keep restore/SQLite/worker startup *inside* the exclusive lifetime.
        try:
            import launch_alpha10 as portable_launcher
            portable_launcher.DATA = data_dir
            portable_launcher.DB = db
            portable_launcher.apply_pending_restore()
        except FileNotFoundError:
            pass

        os.environ["RECRUITMENT_EDITION"] = args.edition
        os.environ["RECRUITMENT_RUNTIME_MODE"] = "desktop" if args.edition == "windows" else "browser"
        os.environ["SRW_BACKGROUND_WORKER"] = "1"

        import uvicorn
        from srw.api.app import create_v1_app

        app = create_v1_app(
            f"sqlite+pysqlite:///{db.as_posix()}",
            frontend_dist=frontend,
            data_dir=data_dir,
            knowledge_dir=knowledge,
        )
        config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
        server = uvicorn.Server(config)
        app.state.shutdown_callback = lambda: setattr(server, "should_exit", True)
        server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
