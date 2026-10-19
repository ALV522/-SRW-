"""Synthetic E3 Core: actual C11 Starlette API with *experimental* Action Plan CAS.

Never run against an existing user workspace. E3 only accepts a fresh empty
temporary directory created by its own launcher, with a guarded marker and
the explicit browser-acceptance environment flag.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
sys.path.insert(0,str(ROOT/"convergence_tests"))

from srw.api.app import create_v1_app
from srw.runtime.db.session import create_v1_engine
from knowledge_fixture import create_minimal_knowledge_tree
from e3_atomic_action_plan import install_e3_action_plan_route

SENTINEL=".srw-e3-throwaway-only"


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--port",type=int,required=True)
    args=parser.parse_args()

    if os.environ.get("SRW_SYNTHETIC_BROWSER_ACCEPTANCE")!="1":
        parser.error("E3 refuses to start without explicitly synthetic test mode")
    workspace=args.workspace.resolve(strict=True)
    if not workspace.is_dir() or workspace.is_symlink():
        parser.error("E3 needs a real, empty throwaway workspace")
    if not (workspace/SENTINEL).is_file():
        parser.error("Missing throwaway E3 marker; refusing to open workspace")
    if (workspace/"data").exists() or (workspace/"knowledge").exists():
        parser.error("Refusing existing SRW database or Knowledge files")
    if not 1024<=args.port<=65535:
        parser.error("E3 port invalid")

    knowledge=create_minimal_knowledge_tree(workspace/"knowledge"/"active")
    data=workspace/"data"
    data.mkdir()
    os.environ["SRW_BACKGROUND_WORKER"]="0"
    database_url=f"sqlite+pysqlite:///{(data/'srw_v1.db').as_posix()}"
    app=create_v1_app(
        database_url,
        data_dir=data,
        knowledge_dir=knowledge,
        frontend_dist=ROOT/"frontend"/"dist",
    )
    # This separate SQLAlchemy Engine connects to the SAME test SQLite file.
    # BEGIN IMMEDIATE ensures revision comparison + business write + audit
    # happen under one database write lock, not a Python proxy mutex.
    engine=create_v1_engine(database_url)
    install_e3_action_plan_route(app,engine)
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=args.port,log_level="warning",access_log=False)


if __name__=="__main__":
    main()
