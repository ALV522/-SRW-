from __future__ import annotations

import multiprocessing
import os
import threading
from pathlib import Path

_SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
_SQLITE_SIDE_SUFFIXES = ("-wal", "-shm", "-journal")


def is_sqlite_fd_target(target: str) -> bool:
    value = str(target or "")
    if value.endswith(" (deleted)"):
        value = value[: -len(" (deleted)")]
    lower = value.lower()
    if lower.endswith(_SQLITE_SUFFIXES):
        return True
    return any(lower.endswith(base + side) for base in _SQLITE_SUFFIXES for side in _SQLITE_SIDE_SUFFIXES)


def _sqlite_open_files() -> list[str]:
    fd_root = Path("/proc/self/fd")
    if not fd_root.is_dir():
        return []
    result: list[str] = []
    for fd in fd_root.iterdir():
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if is_sqlite_fd_target(target):
            result.append(target)
    return sorted(set(result))


def resource_snapshot() -> dict[str, object]:
    return {
        "threads": sorted(
            [
                {"name": t.name, "daemon": bool(t.daemon), "ident": t.ident}
                for t in threading.enumerate()
                if t.ident is not None
            ],
            key=lambda x: (str(x["name"]), int(x["ident"] or 0)),
        ),
        "multiprocessing_children": sorted(
            [
                {"name": p.name, "pid": p.pid}
                for p in multiprocessing.active_children()
                if p.pid is not None
            ],
            key=lambda x: (str(x["name"]), int(x["pid"] or 0)),
        ),
        "sqlite_open_files": _sqlite_open_files(),
    }


def resource_residual(baseline: dict[str, object], final: dict[str, object]) -> dict[str, object]:
    baseline_thread_ids = {x.get("ident") for x in baseline.get("threads", []) if isinstance(x, dict)}
    baseline_child_pids = {x.get("pid") for x in baseline.get("multiprocessing_children", []) if isinstance(x, dict)}
    baseline_sqlite = set(baseline.get("sqlite_open_files", []))
    return {
        "threads": [x for x in final.get("threads", []) if isinstance(x, dict) and x.get("ident") not in baseline_thread_ids],
        "multiprocessing_children": [x for x in final.get("multiprocessing_children", []) if isinstance(x, dict) and x.get("pid") not in baseline_child_pids],
        "sqlite_open_files": [x for x in final.get("sqlite_open_files", []) if x not in baseline_sqlite],
    }


def residual_is_clean(residual: dict[str, object]) -> bool:
    return not any(residual.get(key) for key in ("threads", "multiprocessing_children", "sqlite_open_files"))
