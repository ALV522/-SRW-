from __future__ import annotations

import argparse
from pathlib import Path


def _database_url(path: str) -> str:
    db = Path(path).expanduser().resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+pysqlite:///{db.as_posix()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="srw", description="SRW v1 lean core")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="start the local v1 API")
    serve.add_argument("--db", default="data/srw_v1.db")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--frontend-dist", default="", help="optional built v1 frontend directory")
    serve.add_argument("--data-dir", default="data")
    serve.add_argument("--knowledge-dir", default="knowledge/active")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        # uvicorn is deliberately lazy: importing srw or its CLI does not start/load a server runtime.
        import uvicorn
        from srw.api.app import create_v1_app
        app = create_v1_app(_database_url(args.db), frontend_dist=(args.frontend_dist or None), data_dir=args.data_dir, knowledge_dir=args.knowledge_dir)
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0
    return 2
