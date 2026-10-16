from __future__ import annotations

"""Windows Desktop Host compatibility launcher.

This preserves the stable 0.8.x host ABI while running the Convergence backend.
The WPF host owns the workspace lock and provides instance/session identity in env.
"""

import argparse
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

    # Preserve the Convergence backup/restore semantics before SQLite is opened.
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
