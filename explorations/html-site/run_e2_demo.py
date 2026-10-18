#!/usr/bin/env python3
"""Start the isolated E2 two-client experiment against TEMPORARY real C11 data.

Never attaches to an existing SRW instance. Never accepts --upstream or data
root. A disposable test workspace + actual backend are created on every run,
and E2 can PATCH only the candidate IDs created during that run.

The ETag guard is experimental facade-level concurrency, NOT production-grade
transactional CAS across unmanaged direct backend writers.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from run_e1_demo import ROOT, BACKEND_STARTER, call_json, free_loopback_port, wait_for_backend, create_sample_data
from serve_e1 import select_upstream
from e2_synthetic_bridge import make_synthetic_e2_server


def http_json(base: str, path: str, *, method: str = "GET",
              payload: dict | None = None, etag: str = "") -> tuple[int, dict, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if etag:
        headers["If-Match"] = etag
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), resp.headers.get("ETag", "")
    except urllib.error.HTTPError as exc:
        raw=exc.read()
        try:
            data=json.loads(raw.decode("utf-8"))
        except (ValueError,UnicodeDecodeError):
            data={"text":raw.decode("utf-8",errors="replace")}
        return exc.code, data, exc.headers.get("ETag", "")


def smoke_e2(api: str, web: str, candidate_id: str) -> None:
    path=f"/api/v1/candidates/{candidate_id}/action-plan"
    a,b=http_json(web,path),http_json(web,path)
    if a[0]!=200 or b[0]!=200 or not a[2] or a[2]!=b[2]:
        raise RuntimeError("Two E2 readers must obtain identical Action Plan ETags")
    status, after, updated_etag=http_json(
        web,path,method="PATCH",
        payload={"owner":"Synthetic recruiter A","reason":"first synthetic Web write"},
        etag=a[2],
    )
    if status!=200 or after.get("owner")!="Synthetic recruiter A" or not updated_etag:
        raise RuntimeError(f"E2 conditional write failed: HTTP {status}")
    stale_status, stale_body,_=http_json(
        web,path,method="PATCH",
        payload={"owner":"Synthetic recruiter B","reason":"stale data must not persist"},
        etag=b[2],
    )
    if stale_status!=412 or stale_body.get("error")!="STALE_ACTION_PLAN":
        raise RuntimeError("E2 did not reject the stale second writer")
    persisted=call_json(api,path)
    if persisted.get("owner")!="Synthetic recruiter A":
        raise RuntimeError("Stale update changed authoritative Action Plan")
    no_precondition=http_json(web,path,method="PATCH",payload={"owner":"bad"})
    if no_precondition[0]!=428:
        raise RuntimeError("If-Match was not enforced")
    direct_write=http_json(web,"/api/v1/projects",method="POST",payload={"title":"MUST_NOT_SAVE"})
    if direct_write[0]!=405:
        raise RuntimeError("E2 incorrectly enabled unrelated writes")
    print("E2 smoke PASS: same real Action Plan, conditional write, 412 stale rejection, 428 guard and 405 other writes.",flush=True)


def main() -> int:
    parser=argparse.ArgumentParser(
        description="E2 synthetic-only two-client Action Plan experiment; NEVER attaches to real SRW user data."
    )
    parser.add_argument("--port",type=int,default=0)
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--open-browser",action="store_true")
    args=parser.parse_args()
    if not 0<=args.port<=65535:
        parser.error("--port must be 0-65535")
    backend=None
    server:ThreadingHTTPServer|None=None
    thread:threading.Thread|None=None
    print("SRW E2 synthetic-only conditional-write lab; no EXE or user database",flush=True)
    with tempfile.TemporaryDirectory(prefix="srw-e2-synthetic-") as td:
        logpath=Path(td)/"synthetic-backend.log"
        with logpath.open("w",encoding="utf-8") as logfile:
            try:
                api_port=free_loopback_port()
                api=f"http://127.0.0.1:{api_port}"
                env={**os.environ,"SRW_SYNTHETIC_BROWSER_ACCEPTANCE":"1","PYTHONUNBUFFERED":"1"}
                backend=subprocess.Popen(
                    [sys.executable,"-u",str(BACKEND_STARTER),"--workspace",td,"--port",str(api_port)],
                    cwd=ROOT,env=env,stdout=logfile,stderr=subprocess.STDOUT,
                )
                wait_for_backend(api,backend)
                pid,cid=create_sample_data(api)
                rows=call_json(api,f"/api/v1/projects/{pid}/candidates?archived=active&limit=100")
                candidates={str(c["candidate_id"]) for c in rows.get("candidates",[])}
                if cid not in candidates or len(candidates)<2:
                    raise RuntimeError("Synthetic candidate fixture incomplete")
                upstream,_=select_upstream(supplied_url=api,data_root=None)
                server=make_synthetic_e2_server("127.0.0.1",args.port,upstream=upstream,candidate_ids=candidates)
                web=f"http://127.0.0.1:{server.server_address[1]}"
                print(f"Web: {web}/ — ONLY synthetic Action Plan writes permitted",flush=True)
                print(f"Candidates: {len(candidates)}; all disposable",flush=True)
                if args.smoke:
                    thread=threading.Thread(target=server.serve_forever,daemon=True)
                    thread.start()
                    smoke_e2(api,web,cid)
                    return 0
                if args.open_browser:
                    webbrowser.open(web+"/")
                print("Open two independent browser tabs to test stale If-Match conflicts.",flush=True)
                print("Ctrl+C terminates both services and deletes all synthetic records.",flush=True)
                server.serve_forever()
                return 0
            except KeyboardInterrupt:
                print("\nStopping E2 demo.",flush=True)
                return 0
            except Exception as exc:
                print(f"E2 failed: {type(exc).__name__}: {exc}",file=sys.stderr,flush=True)
                logfile.flush()
                if logpath.exists():
                    lines=logpath.read_text(encoding="utf-8",errors="replace").splitlines()
                    print("\n".join(lines[-10:]),file=sys.stderr)
                return 2
            finally:
                if server is not None:
                    if thread is not None:
                        server.shutdown()
                        thread.join(timeout=5)
                    server.server_close()
                if backend is not None:
                    backend.terminate()
                    try:backend.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        backend.kill();backend.wait(timeout=5)


if __name__=="__main__":
    raise SystemExit(main())
