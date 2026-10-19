"""Launch two disposable SRW Web carrier surfaces on one independently-owned Core.

E4 desktop_surrogate is only a second browser endpoint, NOT Windows WebView2.
Use --smoke for deterministic attach/write/detach/persistence proof.
"""
from __future__ import annotations

import argparse
import time
import urllib.error
import webbrowser

from run_e3_demo import http_json
from run_e1_demo import call_json
from e4_shared_core import launch_shared_e4


def smoke_e4(session):
    a=session.url("web")
    b=session.url("desktop_surrogate")
    identity_a=call_json(a,"/api/v1/runtime/info")
    identity_b=call_json(b,"/api/v1/runtime/info")
    identity_core=session.check_live()
    for key in ("instanceId","sessionId","dataScopeId"):
        if identity_a.get(key)!=identity_b.get(key) or identity_a.get(key)!=identity_core.get(key):
            raise AssertionError(f"Two carriers have different Core {key}")

    path=f"/api/v1/candidates/{session.cid}/action-plan"
    status,first,tag=http_json(a,path)
    if status!=200 or not tag:
        raise AssertionError("Carrier A cannot read revision")
    saved=http_json(
        a,path,method="PATCH",
        payload={"owner":"Carrier A synthetic","reason":"one Core shared by two UI surfaces"},
        etag=tag,
    )
    if saved[0]!=200:
        raise AssertionError("Carrier A conditional write failed")
    remote=http_json(b,path)
    if remote[1].get("owner")!="Carrier A synthetic" or remote[2]!=saved[2]:
        raise AssertionError("Carrier B cannot see shared persistent data")

    pid=session.core.pid
    session.detach("web")
    if session.core.pid!=pid or session.core.poll() is not None:
        raise AssertionError("Detaching Web unexpectedly shut down Core")

    # Desktop surrogate remains usable while the browser-facing proxy is off.
    if http_json(b,path)[1].get("owner")!="Carrier A synthetic":
        raise AssertionError("Remaining carrier lost access after detach")
    saved_b=http_json(
        b,path,method="PATCH",
        payload={"owner":"Carrier B synthetic","reason":"survived other carrier exit"},
        etag=remote[2],
    )
    if saved_b[0]!=200:
        raise AssertionError("Remaining carrier cannot still write")
    if call_json(session.api,path).get("owner")!="Carrier B synthetic":
        raise AssertionError("Core lost post-detach mutation")

    # Even with zero attached UIs, lifecycle is owned by the controller.
    session.detach("desktop_surrogate")
    if session.core.poll() is not None:
        raise AssertionError("Core stopped when final UI was detached")
    detached_read=call_json(session.api,path)
    if detached_read.get("owner")!="Carrier B synthetic":
        raise AssertionError("Core failed to retain state after last detach")
    session.attach("web")
    if http_json(session.url("web"),path)[1].get("owner")!="Carrier B synthetic":
        raise AssertionError("Reattached browser lost authoritative state")

    print("E4 smoke PASS: one Core identity, cross-carrier writes, independent UI detaches and reattach.",flush=True)


def main():
    parser=argparse.ArgumentParser(
        description="Disposable E4 lifecycle lab; NOT a real Windows EXE."
    )
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--open-browser",action="store_true")
    args=parser.parse_args()
    print("SRW E4 shared-Core process ownership laboratory (synthetic only)",flush=True)
    with launch_shared_e4() as session:
        if args.smoke:
            smoke_e4(session)
            return 0
        a=session.url("web")
        b=session.url("desktop_surrogate")
        print("Browser carrier:      "+a+"/",flush=True)
        print("Desktop surrogate:    "+b+"/ (NOT Windows EXE)",flush=True)
        print("Core:                 "+session.api,flush=True)
        print("Both URLs see the same temporary Core. Closing either browser tab does not stop Core.",flush=True)
        print("Stop this controller with Ctrl+C to close both proxies and remove demo data.",flush=True)
        if args.open_browser:
            webbrowser.open(a+"/")
            webbrowser.open(b+"/")
        try:
            while True:
                if session.core.poll() is not None:
                    raise RuntimeError("Shared Core exited unexpectedly")
                time.sleep(0.4)
        except KeyboardInterrupt:
            print("\nStopping independent shared Core and cleaning temporary SQLite.",flush=True)
            return 0


if __name__=="__main__":
    raise SystemExit(main())
