"""Isolated loopback server for real-browser CI acceptance.

Never start against a user workspace. Always use a disposable path provided by
the acceptance runner, and build only synthetic Knowledge fixture databases.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "convergence_tests"))

from knowledge_fixture import create_minimal_knowledge_tree
from srw.api.app import create_v1_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if os.environ.get("SRW_SYNTHETIC_BROWSER_ACCEPTANCE") != "1":
        raise SystemExit("Browser acceptance requires explicit synthetic test mode")
    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir() or workspace.is_symlink():
        raise SystemExit("Acceptance workspace must be a real temporary directory")
    if (workspace / "data").exists() or (workspace / "knowledge").exists():
        raise SystemExit("Acceptance workspace must be empty of SRW data")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Invalid loopback port")

    knowledge = create_minimal_knowledge_tree(workspace / "knowledge" / "active")
    data = workspace / "data"
    data.mkdir()
    os.environ["SRW_BACKGROUND_WORKER"] = "0"
    app = create_v1_app(
        f"sqlite+pysqlite:///{(data / 'srw_v1.db').as_posix()}",
        data_dir=data, knowledge_dir=knowledge,
        frontend_dist=ROOT / "frontend" / "dist",
    )
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
