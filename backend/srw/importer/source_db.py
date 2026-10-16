from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine


def open_legacy_readonly(path: str | Path) -> Engine:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    # SQLAlchemy passes URI parameters to sqlite when uri=true is part of the URL.
    url = f"sqlite+pysqlite:///file:{resolved.as_posix()}?mode=ro&immutable=1&uri=true"
    return create_engine(url, connect_args={"check_same_thread": False})
