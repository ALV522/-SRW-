#!/usr/bin/env python3
"""Launch the *real C11* SRW backend with disposable synthetic data + E1 Web.

No Windows EXE, production data directory, database, user Knowledge or API key
is used. The backend's existing browser_acceptance/serve.py provides a guarded
synthetic-only SQLAlchemy/Starlette runtime and minimal Knowledge fixtures.

The E1 Web remains GET-only. All sample writes occur *before* the Web bridge
is exposed, directly against the disposable server for demo initialization.
Everything is removed on shutdown. Ctrl+C stops both services.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from synthetic_workspace import synthetic_temporary_directory

from serve_e1 import ReadOnlyBridge, select_upstream

ROOT = Path(__file__).resolve().parents[2]
BACKEND_STARTER = ROOT / "browser_acceptance" / "serve.py"


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def call_json(base: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        base + path,
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read(1024 * 1024)
        if response.status != 200:
            raise RuntimeError(f"Synthetic API returned HTTP {response.status}")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("Synthetic API returned an invalid JSON envelope")
        return data


def wait_for_backend(api: str, process: subprocess.Popen, timeout: float = 35) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Synthetic SRW backend exited early (code {process.returncode})")
        try:
            if call_json(api, "/health/ready").get("status") == "ready":
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Synthetic SRW backend did not become ready")


def create_sample_data(api: str) -> tuple[str, str]:
    # This is the only part of the demo that performs writes. The destination
    # is the newly created TEMPORARY acceptance workspace, not a user database.
    slug = uuid.uuid4().hex[:8]
    project = call_json(api, "/api/v1/projects", {
        "title": f"SRW E1 合成演示项目 {slug}",
        "role_title": "招聘分析师（合成岗位）",
        "brief_summary": "纯合成示例：这套数据随演示结束被删除。",
    })
    pid = str(project["project_id"])
    candidate = call_json(api, f"/api/v1/projects/{pid}/candidates", {
        "display_name": "模拟候选人甲（无真实个人信息）",
    })
    cid = str(candidate["candidate_id"])
    call_json(api, f"/api/v1/candidates/{cid}/sources/text", {
        "filename": "synthetic_resume.txt",
        "source_kind": "resume",
        "media_type": "text/plain",
        "text_content": (
            "合成简历材料：具有招聘流程分析、面试排期协调、结构化证据核实经验。"
            "这是人为编写的演示文本，不包含真实简历或个人资料。"
        ),
        "publish_material": True,
    })
    candidate_b = call_json(api, f"/api/v1/projects/{pid}/candidates", {
        "display_name": "模拟候选人乙（无真实个人信息）",
    })
    call_json(api, f"/api/v1/candidates/{candidate_b['candidate_id']}/stage", {
        "stage": "shortlisted",
        "actor": "human",
        "reason": "合成演示：人工推进至短名单",
    })
    return pid, cid


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explore the real SRW C11 Web experience with TEMPORARY synthetic data only."
    )
    parser.add_argument("--port", type=int, default=0, help="E1 browser port, 0 = choose automatically")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Validate both services then exit without a browser")
    args = parser.parse_args()

    if not 0 <= args.port <= 65535:
        parser.error("Invalid --port")
    if not BACKEND_STARTER.is_file():
        parser.error("Missing browser_acceptance/serve.py; use a full exploration-branch checkout")

    backend: subprocess.Popen | None = None
    bridge: ThreadingHTTPServer | None = None
    bridge_thread: threading.Thread | None = None

    print("SRW HTML E1 · Source-based synthetic demo", flush=True)
    print("No EXE is required. Your production database and credentials are never opened.", flush=True)
    with synthetic_temporary_directory(prefix="srw-e1-demo-synthetic-") as workspace:
        api_log = Path(workspace) / "synthetic-backend.log"
        log_handle = api_log.open("w", encoding="utf-8")
        try:
            api_port = free_loopback_port()
            api = f"http://127.0.0.1:{api_port}"
            env = {
                **os.environ,
                "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1",
                "PYTHONUNBUFFERED": "1",
            }
            backend = subprocess.Popen(
                [sys.executable, "-u", str(BACKEND_STARTER),
                 "--workspace", workspace, "--port", str(api_port)],
                cwd=ROOT,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            wait_for_backend(api, backend)
            pid, cid = create_sample_data(api)
            upstream, runtime = select_upstream(supplied_url=api, data_root=None)
            ReadOnlyBridge.upstream = upstream
            bridge = ThreadingHTTPServer(("127.0.0.1", args.port), ReadOnlyBridge)
            ReadOnlyBridge.listen_port = int(bridge.server_address[1])
            web = f"http://127.0.0.1:{ReadOnlyBridge.listen_port}/"

            print(f"Backend: {api} (disposable SQLite)", flush=True)
            print(f"Web:     {web} (GET-only)", flush=True)
            print(f"Version: {runtime.get('version')}", flush=True)
            print("Project and candidate sample records were created in the temporary database.", flush=True)

            if args.smoke:
                bridge_thread = threading.Thread(target=bridge.serve_forever, daemon=True)
                bridge_thread.start()
                info = call_json(web[:-1], "/api/v1/info")
                projects = call_json(web[:-1], "/api/v1/projects")
                candidates = call_json(
                    web[:-1], f"/api/v1/projects/{pid}/candidates?archived=active&limit=100"
                )
                ws = call_json(web[:-1], f"/api/v1/candidates/{cid}/workspace")
                if info.get("product") != "SRW":
                    raise RuntimeError("E1 bridge returned a non-SRW service")
                if not any(p.get("project_id") == pid for p in projects.get("projects", [])):
                    raise RuntimeError("Synthetic project missing from Web")
                if not any(x.get("candidate_id") == cid for x in candidates.get("candidates", [])):
                    raise RuntimeError("Synthetic candidate missing from Web")
                if not ws.get("sources"):
                    raise RuntimeError("Synthetic Source not visible in Web workspace")
                try:
                    call_json(web[:-1], "/api/v1/projects", {
                        "title": "MUST_NOT_PERSIST", "role_title": "blocked",
                    })
                except urllib.error.HTTPError as exc:
                    if exc.code != 405:
                        raise RuntimeError(f"Web mutation must return 405, got {exc.code}") from exc
                else:
                    raise RuntimeError("E1 bridge unexpectedly allowed a write")
                print("E1 source-demo smoke PASS: real backend, shared records and Web write denial.", flush=True)
                return 0

            print("This demo is ONLY synthetic. Exit with Ctrl+C to delete the temporary database.", flush=True)
            print("No OCR/ASR/AI provider calls are made by this demo.", flush=True)
            if args.open_browser:
                webbrowser.open(web)
            bridge.serve_forever()
            return 0
        except KeyboardInterrupt:
            print("\nStopping temporary E1 demo…", flush=True)
            return 0
        except Exception as exc:
            print(f"E1 demo failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            if api_log.exists():
                lines = api_log.read_text(encoding="utf-8", errors="replace").splitlines()
                print("Synthetic backend log (last 12 lines):", file=sys.stderr)
                for line in lines[-12:]:
                    print(line, file=sys.stderr)
            return 2
        finally:
            if bridge is not None:
                bridge.shutdown() if bridge_thread is not None else None
                bridge.server_close()
                if bridge_thread is not None:
                    bridge_thread.join(timeout=4)
            if backend is not None:
                backend.terminate()
                try:
                    backend.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait(timeout=4)
            log_handle.close()
    # TemporaryDirectory deletes synthetic SQLite/Knowledge files here.


if __name__ == "__main__":
    raise SystemExit(main())
