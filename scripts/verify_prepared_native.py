"""Windows native smoke for a prepared, not-yet-accepted SRW C11 payload.

Checks all inventories and Host identity first, executes embedded Windows Python
imports and the actual loopback backend with a disposable workspace, and writes
a separate evidence JSON. Never upgrades release status or edits the package.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

if __package__ in ("", None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.native_payload import (
    PROVENANCE, PayloadError, audit_runtime, read_manifest, sha256_file,
    verified_input, _host_members,
)
from scripts.portable_input_preflight import knowledge_checks
from scripts.check_embedded_runtime_compatibility import check

REQUIRED_IMPORTS = ("anyio", "certifi", "click", "h11", "httpcore", "httpx",
                    "idna", "psutil", "pymupdf", "sqlalchemy", "starlette",
                    "typing_extensions", "uvicorn")
IMPORT_SMOKE = (
    "import importlib,json,sys;"
    "modules=" + repr(REQUIRED_IMPORTS) + ";"
    "loaded={x:importlib.import_module(x).__file__ for x in modules};"
    "assert sys.version_info[:2]==(3,12);"
    "print(json.dumps({'python':sys.version.split()[0],'paths':loaded}))"
)


def _load_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise PayloadError("expected provenance missing or symlinked")
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise PayloadError("provenance must be a JSON object")
    return obj


def inspect_prepared(root: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise PayloadError("application root missing or symbolic link")
    source = read_manifest(root / "SOURCE_MANIFEST.sha256")
    for name, digest in source.items():
        verified_input(root, name, digest)
    runtime = root / "runtime"
    files = audit_runtime(runtime, root / "PRODUCTION_RUNTIME.sha256")["files"]
    checks = knowledge_checks(root / "knowledge" / "active", root / "PRODUCTION_KNOWLEDGE.sha256")
    if len(checks) != 6 or any(x["status"] != "PASS" for x in checks):
        raise PayloadError("Knowledge SQLite/hash checks blocked")
    dependency = check(runtime, root / "requirements-ci.txt")
    if (dependency["status"] != "PINNED_METADATA_MATCH"
        or dependency.get("c11_overlay_on_path") is not True):
        raise PayloadError("effective embedded Python overlay does not satisfy C11 lock")

    host = root / "windows-host"
    host_files = _host_members(host)
    expected_host_sha = host_files["windows-host/SmartRecruitmentWorkbench.exe"]
    host_meta = _load_json(host / "HOST_BUILD_CANDIDATE.json")
    host_truth = _load_json(host / "DOTNET_BUILD_TRUTH.json")
    context = _load_json(root / PROVENANCE)
    git_sha = context.get("host_source_git_sha")
    if not isinstance(git_sha, str) or len(git_sha) != 40:
        raise PayloadError("invalid exact source SHA")
    if (host_meta.get("git_sha") != git_sha or
        host_meta.get("host_sha256") != expected_host_sha or
        host_meta.get("status") != "COMPILED_ONLY_UNVERIFIED_GUI" or
        host_meta.get("gui_accepted") is not False or
        host_truth.get("source_git_sha") != git_sha or
        (host_truth.get("outputs") or {}).get("executable_sha256") != expected_host_sha):
        raise PayloadError("Host build identity mismatch")
    # Reject unknown extra files in the extracted payload, including local
    # secrets, candidate data and unreviewed backup directories.
    expected_paths = (
        set(source) |
        {"SOURCE_MANIFEST.sha256", "PRODUCTION_RUNTIME.sha256",
         "PRODUCTION_KNOWLEDGE.sha256", PROVENANCE} |
        {"runtime/" + rel for rel in read_manifest(root / "PRODUCTION_RUNTIME.sha256", runtime=True)} |
        {"knowledge/active/" + rel for rel in read_manifest(root / "PRODUCTION_KNOWLEDGE.sha256")} |
        set(host_files)
    )
    actual_paths = set()
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise PayloadError("symlink in extracted Native package")
        if candidate.is_file():
            actual_paths.add(candidate.relative_to(root).as_posix())
    if actual_paths != expected_paths:
        # Show only names/counts, never disclose file contents. Unknown inputs
        # remain blocked; Python-created .pyc cannot silently change release truth.
        extra = sorted(actual_paths - expected_paths)
        missing = sorted(expected_paths - actual_paths)
        raise PayloadError(
            "extracted Native candidate contains missing or unreviewed files "
            f"(unexpected_count={len(extra)}, missing_count={len(missing)}, "
            f"unexpected_sample={extra[:12]!r}, missing_sample={missing[:12]!r})"
        )
    if (context.get("artifact_status") != "UNVERIFIED_GUI" or
        context.get("prepared_status") != "OFFLINE_WHEELS_STAGED_NEEDS_WINDOWS_EMBEDDED_SMOKE" or
        context.get("embedded_python_windows_smoke_passed") is not False or
        context.get("windows_gui_accepted") is not False or
        context.get("target_version") != (root / "VERSION").read_text(encoding="utf-8").strip() or
        context.get("source_manifest_sha256") != sha256_file(root / "SOURCE_MANIFEST.sha256") or
        context.get("runtime_manifest_sha256") != sha256_file(root / "PRODUCTION_RUNTIME.sha256") or
        context.get("knowledge_manifest_sha256") != sha256_file(root / "PRODUCTION_KNOWLEDGE.sha256") or
        context.get("host_executable_sha256") != expected_host_sha):
        raise PayloadError("prepared payload provenance mismatch")
    return {
        "source_file_count": len(source), "runtime_file_count": files,
        "knowledge_databases": 5, "host_members": len(host_files),
        "pinned_dependencies": dependency["matched"],
        "source_sha": git_sha,
        "status": "PREPARED_STATIC_PASS_WINDOWS_SMOKE_NOT_YET_RUN",
    }


def _probe(url: str, timeout: float) -> dict:
    with urlopen(Request(url, headers={"User-Agent": "SRW-C11-local-smoke"}), timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("backend returned non-200 readiness")
        return json.loads(response.read(262144).decode("utf-8"))


def _ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _smoke_host_owned_core(root: Path, *, python: Path, env: dict[str, str],
                           port: int, instance: str, session: str,
                           token: str, startup_timeout: int) -> None:
    """Run the actual Host-mode Core with a real *parent-owned* synthetic lease.

    Modern run_local.py deliberately refuses --workspace-lock host when the
    immediate parent does not own the exact schema-v2 lease. A verifier cannot
    bypass that security check merely by setting Host identity variables.
    This parent process stands in for WPF only inside a disposable workspace.
    """
    import importlib.util

    lease_path = (root / "backend" / "srw" / "workspace_lease.py").resolve(strict=True)
    # Load the exact already-manifest-verified source from the candidate,
    # independent of any site-packages or an external verifier's sys.modules.
    # This is a standalone module with no package-relative dependencies.
    spec = importlib.util.spec_from_file_location("_srw_native_candidate_host_lease", lease_path)
    if spec is None or spec.loader is None:
        raise PayloadError("embedded backend lease source unavailable")
    lease_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = lease_module  # dataclasses resolves __module__ here
    write_bytecode_before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # NEVER dirty the immutable Native candidate
    try:
        spec.loader.exec_module(lease_module)
    finally:
        sys.modules.pop(spec.name, None)
        sys.dont_write_bytecode = write_bytecode_before
    data = Path(env["RECRUITMENT_DATA_DIR"]).resolve()
    command = [str(python), "-B", str(root / "scripts" / "run_local.py"),
               "--host", "127.0.0.1", "--port", str(port),
               "--edition", "windows", "--workspace-lock", "host"]
    # The lease owner and Popen parent MUST be the same real process. Do not
    # synthesize another PID or permit a child to set its own WPF lease.
    with lease_module.WorkspaceLease(
        data, edition="windows", port=port,
        instance_id=instance, session_id=session,
    ):
        with tempfile.TemporaryFile(mode="w+b") as stderr:
            with subprocess.Popen(command, cwd=root, env=env,
                                  stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=stderr) as process:
                try:
                    deadline = time.monotonic() + startup_timeout
                    last_error = None
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            # No raw stderr or tokens in public acceptance
                            # reports. Emit only the recognized failure type.
                            stderr.seek(0)
                            diagnostic = stderr.read(16384).decode("utf-8", "replace")
                            category = ("HOST_WORKSPACE_INVALID" if "HOST_WORKSPACE_INVALID" in diagnostic
                                        else "BACKEND_STARTUP_ERROR")
                            raise PayloadError(
                                f"embedded Windows backend exited before readiness "
                                f"(exit_code={process.returncode}, category={category})"
                            )
                        try:
                            ready = _probe(f"http://127.0.0.1:{port}/api/v1/runtime/ready", 1)
                            if ready.get("status") == "ready":
                                break
                        except (OSError, URLError, ValueError) as exc:
                            last_error = type(exc).__name__
                        time.sleep(0.2)
                    else:
                        raise PayloadError("Windows backend did not become ready: " + str(last_error))
                    info = _probe(f"http://127.0.0.1:{port}/api/v1/runtime/info", 3)
                    if (info.get("instanceId") != instance or
                        info.get("sessionId") != session or
                        info.get("edition") != "windows" or
                        info.get("runtime") != "desktop"):
                        raise PayloadError("embedded backend Host ABI identity mismatch")
                    try:
                        request = Request(
                            f"http://127.0.0.1:{port}/api/v1/runtime/shutdown",
                            data=b"", method="POST", headers={"X-SRW-Session": token},
                        )
                        with urlopen(request, timeout=3):
                            pass
                    except OSError:
                        pass
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=6)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=6)


def smoke_windows(root: Path, *, startup_timeout: int = 45) -> dict:
    if os.name != "nt":
        raise PayloadError("Windows embedded Python and WPF Host require a real Windows x64 runner")
    python = root / "runtime" / "python.exe"
    imports = subprocess.run(
        [str(python), "-I", "-B", "-c", IMPORT_SMOKE],
        cwd=root, capture_output=True, text=True, timeout=90, check=False,
    )
    if imports.returncode:
        raise PayloadError("embedded Python import smoke failed: " + imports.stderr[-800:])
    try:
        module_truth = json.loads(imports.stdout.strip())
        paths = module_truth["paths"]
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise PayloadError("embedded Python smoke JSON malformed") from exc
    if set(paths) != set(REQUIRED_IMPORTS):
        raise PayloadError("unexpected embedded Python imported modules")
    runtime_root = (root / "runtime").resolve()
    for path in paths.values():
        if not isinstance(path, str) or not Path(path).resolve().is_relative_to(runtime_root):
            raise PayloadError("embedded Python used an external Python package")
    port = _ephemeral_port()
    token = uuid.uuid4().hex
    instance = "synthetic-" + uuid.uuid4().hex
    session = "synthetic-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="srw-c11-windows-smoke-") as td:
        env = os.environ.copy()
        env.update({
            "RECRUITMENT_DATA_DIR": str(Path(td) / "data"),
            "RECRUITMENT_KNOWLEDGE_DIR": str(root / "knowledge"),
            "RECRUITMENT_FRONTEND_DIST": str(root / "frontend" / "dist"),
            "RECRUITMENT_EDITION": "windows",
            "RECRUITMENT_RUNTIME_MODE": "desktop",
            "RECRUITMENT_INSTANCE_ID": instance,
            "RECRUITMENT_SESSION_ID": session,
            "RECRUITMENT_SESSION_TOKEN": token,
            "RECRUITMENT_RELEASE_ID": str(_load_json(root / "BUILD_INFO.json").get("release_id", "")),
            "SRW_BACKGROUND_WORKER": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        # Stand in for the WPF parent using an actual schema-v2 lease held
        # across real child startup, HTTP readiness and shutdown. This keeps
        # the production Host-parent single-writer contract fully enforced.
        _smoke_host_owned_core(
            root, python=python, port=port, env=env, instance=instance,
            session=session, token=token, startup_timeout=startup_timeout,
        )
        return {
            "status": "EMBEDDED_PYTHON_AND_LOOPBACK_BACKEND_SMOKE_PASS",
            "python": module_truth["python"],
            "modules_imported": sorted(paths),
            "backend_identity_verified": True,
            "synthetic_workspace": True,
            "wpf_webview2_gui_accepted": False,
        }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--static-only", action="store_true")
    args = p.parse_args()
    root = args.root.resolve(strict=True)
    evidence = args.evidence.resolve()
    if evidence.is_relative_to(root):
        raise SystemExit("evidence must be outside the immutable application payload")
    try:
        # Fail before any process launch if a previous evidence file exists.
        # A new run must use a unique evidence path to preserve earlier results.
        if evidence.exists():
            raise PayloadError("evidence file already exists; provide a new --evidence path")
        report = inspect_prepared(root)
        if not args.static_only:
            report["windows_runtime_smoke"] = smoke_windows(root)
        report["gui_accepted"] = False
        report["status"] = "STATIC_PASS_WINDOWS_SMOKE_PENDING" if args.static_only else "WINDOWS_BACKEND_SMOKE_PASS_GUI_PENDING"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (PayloadError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
