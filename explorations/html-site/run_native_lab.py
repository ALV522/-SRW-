"""Start SOURCE-backed experimental Windows WPF host + genuine C11 Core.

No existing app data is opened, no real candidate data is used. A temporary
data directory is created for the WPF host, and only synthetic Knowledge
fixtures are used. Runtime is a local Python 3.12 venv created in the
extracted experiment; this package is NOT standalone or release portable.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
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

ROOT=Path(__file__).resolve().parent
APP=ROOT/"app"
sys.path.insert(0,str(APP/"convergence_tests"))
sys.path.insert(0,str(APP/"explorations"/"html-site"))
from knowledge_fixture import create_minimal_knowledge_tree
from synthetic_workspace import synthetic_temporary_directory
from serve_e1 import ReadOnlyBridge,select_upstream,probe_json

KNOWLEDGE_MARKER=".srw-synthetic-knowledge-lab"
EXPECTED_DBS=("taxonomy","job_info","competency","market_reference","reference")


def setup_runtime():
    if platform.system()!="Windows":
        raise RuntimeError("Native WPF preview requires Windows")
    if sys.version_info[:2]!=(3,12):
        raise RuntimeError("Native WPF source preview requires Python 3.12")
    runtime=APP/"runtime"
    native_python=runtime/"Scripts"/"python.exe"
    if not (runtime/"Scripts"/"python.exe").is_file():
        if runtime.exists():
            raise RuntimeError("Existing incomplete runtime directory; do not overwrite manually")
        print("Creating isolated Python 3.12 virtual environment for the SOURCE demo.",flush=True)
        subprocess.run([sys.executable,"-m","venv",str(runtime)],check=True)
    script=runtime/"Scripts"/"python.exe"
    sentinel=runtime/".native-synthetic-deps.ready"
    if not sentinel.is_file():
        print("Installing pinned synthetic C11 dependencies in isolated venv…",flush=True)
        subprocess.run([str(script),"-m","pip","install","--disable-pip-version-check",
                        "-r",str(APP/"requirements-ci.txt")],check=True)
        sentinel.write_text("verified pinned CI requirements",encoding="utf-8")
    # The isolated lab Host uses an explicitly SOURCE-LAB-patched AppPaths:
    # it launches runtime/Scripts/python.exe directly, preserving pyvenv.cfg.
    # Never copy the redirector to runtime/python.exe: that loses venv context.
    check=subprocess.run(
        [str(native_python),"-c",
         "import sys,uvicorn,sqlalchemy,starlette; print(sys.prefix)"],
        text=True,capture_output=True,timeout=12
    )
    if check.returncode!=0:
        raise RuntimeError("runtime/Scripts/python.exe cannot access venv packages; "+
                           (check.stderr or check.stdout)[-600:])
    if Path(check.stdout.strip()).resolve()!=runtime.resolve():
        raise RuntimeError("runtime/Scripts/python.exe escaped its isolated venv")
    return native_python


def setup_synthetic_knowledge():
    root=APP/"knowledge"
    if root.exists():
        if not (root/KNOWLEDGE_MARKER).is_file():
            raise RuntimeError("Existing Knowledge directory is not marked synthetic; refusing to modify")
    else:
        root.mkdir()
        create_minimal_knowledge_tree(root/"active")
        (root/KNOWLEDGE_MARKER).write_text(
            "SYNTHETIC E1-E5 test Knowledge only; NOT production resources.",
            encoding="utf-8"
        )
    for name in EXPECTED_DBS:
        path=root/"active"/name/"knowledge.db"
        if not path.is_file() or path.read_bytes()[:16]!=b"SQLite format 3\x00":
            raise RuntimeError("Missing/invalid synthetic Knowledge fixture: "+name)


def wait_for_host(process, data:Path, *, seconds=50):
    deadline=time.monotonic()+seconds
    lease=data/"app.lock"/"instance.json"
    last_error="lease not yet published"
    while time.monotonic()<deadline:
        if process.poll() is not None:
            raise RuntimeError(f"WPF Host exited before C11 readiness (exit={process.returncode})")
        try:
            if lease.is_file():
                upstream,identity=select_upstream(supplied_url=None,data_root=str(data))
                ready=probe_json(upstream,"/api/v1/runtime/ready")
                if ready.get("status")=="ready":
                    if identity.get("edition")!="windows" or identity.get("runtime")!="desktop":
                        raise RuntimeError("Runtime is not the Windows host-owned C11 Core")
                    return upstream,identity
                last_error="runtime/ready is not ready"
        except (OSError,ValueError,urllib.error.URLError,
                urllib.error.HTTPError,KeyError,json.JSONDecodeError) as exc:
            last_error=type(exc).__name__+": "+str(exc)
        time.sleep(.25)
    raise RuntimeError("WPF Host Core readiness timeout: "+last_error)


def wait_gui_log(data:Path,*,seconds=15):
    log=data/"logs"/"host.log"
    deadline=time.monotonic()+seconds
    seen=set()
    while time.monotonic()<deadline:
        if log.is_file():
            for line in log.read_text(encoding="utf-8",errors="replace").splitlines():
                try: event=json.loads(line).get("event")
                except ValueError: continue
                if event in ("webview_initialized","frontend_loaded","webview_failed"):
                    seen.add(event)
            if "frontend_loaded" in seen or "webview_failed" in seen:
                return sorted(seen)
        time.sleep(.25)
    return sorted(seen)


def start_web_bridge(upstream:str):
    handler=type("WpfSourceLabE1",(ReadOnlyBridge,),{
        "upstream":upstream,
        "listen_port":0
    })
    server=ThreadingHTTPServer(("127.0.0.1",0),handler)
    handler.listen_port=server.server_address[1]
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    return server,thread,f"http://127.0.0.1:{server.server_address[1]}"


def smoke_shared_web(upstream,web):
    # Test a Web viewer attached to a *host-owned* C11 Core, not E3's mock desktop.
    from urllib.request import Request,urlopen
    import uuid
    name="NativeHost-C11-Synthetic-"+uuid.uuid4().hex[:8]
    payload=json.dumps({
        "title":name,
        "role_title":"Synthetic native-host business smoke",
        "brief_summary":"Ephemeral Windows WPF + real SRW backend + browser read-only test",
    },ensure_ascii=False).encode("utf-8")
    req=Request(upstream+"/api/v1/projects",data=payload,method="POST",
                headers={"Content-Type":"application/json","Accept":"application/json"})
    with urlopen(req,timeout=6) as response:
        obj=json.loads(response.read().decode("utf-8"))
    pid=obj["project_id"]
    with urlopen(web+"/api/v1/projects",timeout=5) as response:
        projects=json.loads(response.read().decode("utf-8")).get("projects",[])
    if not any(x.get("project_id")==pid and x.get("title")==name for x in projects):
        raise RuntimeError("Web E1 did not observe C11 Windows Native Host's project")
    with urlopen(web+"/",timeout=5) as response:
        if b"SRW" not in response.read():
            raise RuntimeError("E1 HTML not served alongside Native Host")
    try:
        req=Request(web+"/api/v1/projects",data=payload,method="POST")
        urlopen(req,timeout=5)
    except urllib.error.HTTPError as exc:
        if exc.code!=405:
            raise RuntimeError(f"Web mutation returned HTTP {exc.code}, expected 405")
    else:
        raise RuntimeError("Read-only attached Web unexpectedly permitted POST")
    print("Native WPF host + E1 Web share actual C11 Core/SQLite: PASS",flush=True)


def main():
    p=argparse.ArgumentParser(
        description="Source-only Native WPF + real SRW C11 synthetic GUI experiment"
    )
    p.add_argument("--smoke",action="store_true")
    p.add_argument("--strict-gui",action="store_true",
                   help="Require frontend_loaded in Windows Host log")
    p.add_argument("--web-browser",action="store_true",
                   help="Open E1 read-only browser alongside WPF host")
    args=p.parse_args()
    host=APP/"windows-host"/"SmartRecruitmentWorkbench.exe"
    for path in [host,APP/"VERSION",APP/"BUILD_INFO.json",
                 APP/"scripts"/"run_local.py",APP/"frontend"/"dist"/"index.html"]:
        if not path.is_file():
            p.error("Complete Native SOURCE Lab extraction required; missing "+str(path))
    setup_runtime()
    setup_synthetic_knowledge()

    proc=None
    web_server=None
    web_thread=None
    print("SRW Native SOURCE lab: Windows EXE + C11 backend, all recruitment data synthetic.",flush=True)
    with synthetic_temporary_directory("srw-native-lab-") as td:
        data=Path(td)
        try:
            proc=subprocess.Popen([
                str(host),"--application-root",str(APP),"--data-root",str(data)
            ],cwd=str(APP),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            upstream,identity=wait_for_host(proc,data)
            print("WPF Host-owned Core ready: "+str(identity.get("version")),flush=True)
            web_server,web_thread,web=start_web_bridge(upstream)
            smoke_shared_web(upstream,web)
            gui=wait_gui_log(data,seconds=8 if args.smoke else 15)
            print("Native GUI events: "+str(gui),flush=True)
            if args.strict_gui and "frontend_loaded" not in gui:
                raise RuntimeError("WPF GUI/WebView2 frontend_loaded was not observed")
            if args.smoke:
                print("Native SOURCE demo smoke PASS (backend + Web E1, GUI verdict above).",flush=True)
                return 0
            print("Web E1 read-only URL: "+web+"/",flush=True)
            print("Close the WPF window to end the temporary session.",flush=True)
            if args.web_browser:
                webbrowser.open(web+"/")
            proc.wait()
            print("WPF Host closed; temporary SRW database will be removed.",flush=True)
            return 0
        except Exception:
            log=data/"logs"/"host.log"
            if log.is_file():
                # Do not print raw files/paths/candidate contents.
                seen=[]
                for line in log.read_text(encoding="utf-8",errors="replace").splitlines()[-25:]:
                    try: event=json.loads(line).get("event","")
                    except ValueError: continue
                    seen.append(event)
                print("Native Host recent event TYPES only: "+str(seen),flush=True)
            raise
        finally:
            if web_server:
                web_server.shutdown()
                web_server.server_close()
                if web_thread:
                    web_thread.join(timeout=4)
            if proc:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__=="__main__":
    raise SystemExit(main())
