from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from srw.runtime.backup_truth import (extract_validated_backup, write_backup_archive)
DATA = ROOT / "data"
DB = DATA / "srw_v1.db"
FRONTEND = ROOT / "frontend" / "dist"
KNOWLEDGE = ROOT / "knowledge" / "active"
EXPECTED_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
EXPECTED_SCHEMA = "v1_0014"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def data_dir_identity(path: Path | None = None) -> str:
    resolved = (path or DATA).resolve()
    return hashlib.sha256(os.path.normcase(str(resolved)).encode("utf-8")).hexdigest()


def classify_existing(info: dict, expected_identity: str) -> str:
    if info.get("product") != "SRW":
        return "ignore"
    if info.get("data_dir_identity") != expected_identity:
        return "ignore"
    return "reuse" if info.get("version") == EXPECTED_VERSION else "conflict"


def find_existing() -> tuple[str, int | None, dict | None]:
    expected = data_dir_identity()
    for port in range(8765, 8786):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/info", timeout=.25) as r:
                obj = json.loads(r.read().decode())
            kind = classify_existing(obj, expected)
            if kind != "ignore":
                return kind, port, obj
        except Exception:
            pass
    return "none", None, None


class InstanceLock:
    """Cross-platform advisory lock held for the whole Portable server lifetime."""

    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        if os.path.getsize(self.path) == 0:
            os.write(fd, b"0")
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            os.close(fd)
            raise RuntimeError("this SRW data directory is already locked by another process")
        self.fd = fd

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            os.lseek(self.fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()


def _safe_backup_name(name: str) -> str:
    p = Path(name).name
    if p != name or not p.lower().endswith(".zip"):
        raise RuntimeError("invalid backup name")
    return p


def _read_schema(db: Path) -> str:
    if not db.is_file() or db.read_bytes()[:16] != b"SQLite format 3\x00":
        raise RuntimeError("invalid backup database")
    conn = sqlite3.connect(str(db), timeout=2.0)
    try:
        qc = conn.execute("PRAGMA quick_check").fetchone()
        if not qc or str(qc[0]).lower() != "ok":
            raise RuntimeError("backup database failed SQLite quick_check")
        row = conn.execute("SELECT schema_revision FROM v1_schema_meta LIMIT 1").fetchone()
        if not row:
            raise RuntimeError("backup database has no SRW schema revision")
        return str(row[0])
    finally:
        conn.close()


def _pre_restore_backup() -> Path | None:
    if not DB.exists():
        return None
    backups = DATA / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    dest = backups / f"pre_restore-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    with tempfile.TemporaryDirectory(prefix="srw-prerestore-", dir=DATA) as td:
        snap = Path(td) / "srw_v1.db"
        src = sqlite3.connect(str(DB)); dst = sqlite3.connect(str(snap))
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        write_backup_archive(dest, snap, DATA / "blobs")
    return dest


def apply_pending_restore() -> str | None:
    # Journal verification and recovery run before any Core database access.
    # No unknown rollback material is removed without a matching transaction.
    from srw.runtime.restore_transaction import apply_restore
    return apply_restore(DATA, DB, EXPECTED_SCHEMA, _pre_restore_backup, _read_schema)

def self_check() -> int:
    result = {"ok": True, "checks": {}}
    try:
        if sys.version_info[:2] != (3, 12):
            raise RuntimeError(f"expected embedded Python 3.12, got {sys.version.split()[0]}")
        result["checks"]["python"] = "3.12"
        import importlib.metadata as md
        required = {
            "SQLAlchemy":"2.0.43", "starlette":"0.47.3", "uvicorn":"0.35.0", "httpx":"0.28.1",
            "PyMuPDF":"1.26.4", "python-docx":"1.2.0", "openpyxl":"3.1.5", "python-multipart":"0.0.32",
        }
        versions = {}
        for pkg, want in required.items():
            got = md.version(pkg)
            if got != want: raise RuntimeError(f"{pkg} {got} != {want}")
            versions[pkg] = got
        result["checks"]["packages"] = versions
        for p in (FRONTEND/"index.html", FRONTEND/"app.js", FRONTEND/"styles.css", ROOT/"backend"/"srw"/"release_state.json"):
            if not p.is_file(): raise RuntimeError(f"missing file: {p.relative_to(ROOT)}")
        for name in ("taxonomy", "job_info", "competency", "market_reference", "reference"):
            p = KNOWLEDGE / name / "knowledge.db"
            if not p.is_file() or p.read_bytes()[:16] != b"SQLite format 3\x00":
                raise RuntimeError(f"knowledge database invalid: {name}")
        from srw.api.app import create_v1_app
        # Validate the application without writing a real user data directory
        # into the package staging tree during native assembly.
        with tempfile.TemporaryDirectory(prefix="srw-native-self-check-") as td:
            create_v1_app("sqlite+pysqlite:///:memory:", data_dir=Path(td) / "data", knowledge_dir=KNOWLEDGE, frontend_dist=FRONTEND)
        from srw.release import get_release_state
        release = get_release_state()
        if release["version"] != EXPECTED_VERSION or release["schema_revision"] != EXPECTED_SCHEMA:
            raise RuntimeError(f"unexpected release state: {release}")
        result["checks"]["release"] = f"{release['version']} / {release['schema_revision']}"
        result["checks"]["app"] = "created with in-memory SQLite"
    except Exception as exc:
        result["ok"] = False; result["error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def free_port() -> int:
    for port in range(8765, 8786):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port)); return port
        except OSError:
            pass
        finally:
            s.close()
    raise RuntimeError("no free local port in 8765-8785")


def open_when_ready(port: int) -> None:
    url = f"http://127.0.0.1:{port}/v1"
    for _ in range(160):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=.4) as r:
                if r.status == 200:
                    webbrowser.open(url); return
        except Exception:
            time.sleep(.15)
    print("服务未在预期时间内就绪，请查看本窗口日志。")


def _resolve_old_data(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if (p / "srw_v1.db").is_file(): return p
    if (p / "data" / "srw_v1.db").is_file(): return p / "data"
    raise RuntimeError("所选目录中未找到 data\\srw_v1.db 或 srw_v1.db")


def migrate_from(path: str) -> int:
    from srw.runtime.portable_migration import migrate_data_directory
    source = _resolve_old_data(path)
    result = migrate_data_directory(source, DATA)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("迁移完成。旧目录未被修改；现在可以运行 START.bat。")
    return 0


def serve() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    kind, port, info = find_existing()
    if kind == "reuse":
        print(f"检测到同一 Business Convergence 08 数据目录已在运行：http://127.0.0.1:{port}/v1")
        webbrowser.open(f"http://127.0.0.1:{port}/v1")
        return 0
    if kind == "conflict":
        raise RuntimeError(f"同一数据目录正被另一 SRW 版本占用：{info.get('version') if info else 'unknown'}")

    with InstanceLock(DATA / ".srw-instance.lock"):
        # Close the race between discovery and lock acquisition.
        kind, port, info = find_existing()
        if kind == "reuse":
            webbrowser.open(f"http://127.0.0.1:{port}/v1"); return 0
        if kind == "conflict":
            raise RuntimeError(f"同一数据目录正被另一 SRW 版本占用：{info.get('version') if info else 'unknown'}")
        restored = apply_pending_restore()
        if restored: print(f"已在数据库打开前恢复备份：{restored}")
        port = free_port()
        threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()
        print("SRW v1.0 Business Convergence 08 · 0.8 Capability Recovery")
        print(f"本地地址：http://127.0.0.1:{port}/v1")
        print("按 Ctrl+C 停止服务。")
        # Real Portable servers must execute durable Task/Job queues in the background.
        os.environ["SRW_BACKGROUND_WORKER"] = "1"
        from srw.cli import main as srw_main
        return srw_main([
            "serve", "--db", str(DB), "--host", "127.0.0.1", "--port", str(port),
            "--frontend-dist", str(FRONTEND), "--data-dir", str(DATA), "--knowledge-dir", str(KNOWLEDGE),
        ])


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--migrate-from", default="")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check: return self_check()
    if args.migrate_from: return migrate_from(args.migrate_from)
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
