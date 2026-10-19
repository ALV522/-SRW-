"""E4 lab: independent owner of ONE disposable SRW Core + TWO UI carriers.

Desktop here is explicitly a *browser/WebView2 surrogate*, not a native EXE.
Closing the browser-facing proxy must not terminate the separately supervised
Core nor the other attached carrier.

Never accepts an existing data root, upstream, production credentials or real
candidate files. The only supported workspace is newly created in a temporary
directory; the Core uses the E3 synthetic transactional Action Plan route.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from run_e1_demo import ROOT, call_json, free_loopback_port, wait_for_backend, create_sample_data
from e3_web_bridge import make_synthetic_e3_server
from synthetic_workspace import synthetic_temporary_directory
from serve_e1 import select_upstream

E3_CORE = Path(__file__).resolve().parent / "e3_core_server.py"


@dataclass
class SharedCoreSession:
    api: str
    pid: str
    cid: str
    core: subprocess.Popen
    _servers: dict = field(default_factory=dict)
    _threads: dict = field(default_factory=dict)
    _candidates: set[str] = field(default_factory=set)

    def attach(self, carrier: str) -> str:
        if carrier not in {"web", "desktop_surrogate"}:
            raise ValueError("Only two explicitly synthetic UI carriers are supported")
        if carrier in self._servers:
            raise ValueError("Carrier already attached")
        if self.core.poll() is not None:
            raise RuntimeError("E4 Core has already stopped")
        upstream,_ = select_upstream(supplied_url=self.api, data_root=None)
        server = make_synthetic_e3_server(
            "127.0.0.1", 0, upstream=upstream,
            candidate_ids=self._candidates,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._servers[carrier]=server
        self._threads[carrier]=thread
        return f"http://127.0.0.1:{server.server_address[1]}"

    def detach(self, carrier: str) -> None:
        server=self._servers.pop(carrier,None)
        thread=self._threads.pop(carrier,None)
        if server:
            server.shutdown()
            server.server_close()
            if thread:
                thread.join(timeout=5)
        # DO NOT touch self.core here. The shared owner, not the carrier,
        # controls Core lifecycle and SQLite/Knowledge worker ownership.

    def check_live(self) -> dict:
        if self.core.poll() is not None:
            raise RuntimeError("Single shared C11 Core is no longer running")
        live=call_json(self.api,"/api/v1/runtime/info")
        if live.get("product")!="SRW":
            raise RuntimeError("E4 Core identity invalid")
        return live

    def close_carriers(self) -> None:
        for name in tuple(self._servers):
            self.detach(name)


@contextmanager
def launch_shared_e4() -> Iterator[SharedCoreSession]:
    with synthetic_temporary_directory("srw-e4-synthetic-") as td:
        path=Path(td)
        (path/".srw-e3-throwaway-only").write_text("single-core demo",encoding="utf-8")
        logpath=path/"core.log"
        core=None
        session=None
        with logpath.open("w",encoding="utf-8") as logfile:
            try:
                port=free_loopback_port()
                api=f"http://127.0.0.1:{port}"
                env={
                    **os.environ,
                    "SRW_SYNTHETIC_BROWSER_ACCEPTANCE":"1",
                    "PYTHONUNBUFFERED":"1",
                }
                core=subprocess.Popen(
                    [sys.executable,"-u",str(E3_CORE),
                     "--workspace",td,"--port",str(port)],
                    cwd=ROOT,env=env,
                    stdout=logfile,stderr=subprocess.STDOUT,
                )
                wait_for_backend(api,core)
                pid,cid=create_sample_data(api)
                rows=call_json(api,f"/api/v1/projects/{pid}/candidates?archived=active&limit=100")
                candidates={str(row["candidate_id"]) for row in rows.get("candidates",[])}
                if cid not in candidates or len(candidates)<2:
                    raise RuntimeError("E4 synthetic candidate initialization failed")
                session=SharedCoreSession(
                    api=api,pid=pid,cid=cid,core=core,_candidates=candidates,
                )
                session.attach("web")
                session.attach("desktop_surrogate")
                yield session
            except Exception:
                logfile.flush()
                if core and core.poll() is not None and logpath.is_file():
                    print("E4 Core start diagnostics (synthetic only):",flush=True)
                    print("\n".join(logpath.read_text(encoding="utf-8",errors="replace").splitlines()[-12:]),flush=True)
                raise
            finally:
                if session:
                    session.close_carriers()
                if core:
                    core.terminate() if core.poll() is None else None
                    try: core.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        core.kill()
                        core.wait(timeout=5)
