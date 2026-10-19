"""Fail-closed cleanup of temporary SRW synthetic workspaces on Windows.

SQLite + antivirus/file-indexer may briefly hold filesystem handles even after
the owner process has terminated. Retry boundedly; NEVER silently ignore
cleanup failure or delete any path that was not created by this context.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def synthetic_temporary_directory(
    prefix: str, *, attempts: int = 40, retry_seconds: float = 0.25
) -> Iterator[str]:
    if not prefix.startswith("srw-e") or "/" in prefix or "\\" in prefix:
        raise ValueError("Only SRW exploration temporary prefixes are allowed")
    if attempts < 1 or retry_seconds < 0:
        raise ValueError("Cleanup retries must be bounded and nonnegative")
    path = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    try:
        yield str(path)
    finally:
        previous_error = None
        for attempt in range(attempts):
            try:
                shutil.rmtree(path)
                if path.exists():
                    raise OSError("Synthetic workspace directory still exists")
                print("Synthetic SRW workspace removed.", flush=True)
                break
            except (OSError, PermissionError) as exc:
                previous_error = exc
                if attempt + 1 < attempts:
                    time.sleep(retry_seconds)
        else:
            raise RuntimeError(
                "Synthetic workspace cleanup failed after bounded retries. "
                "Confirm no SRW demo processes remain and delete this TEMPORARY "
                f"directory manually: {path}"
            ) from previous_error
