from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class V1Base(DeclarativeBase):
    """Independent SQLAlchemy metadata for the SRW v1 database."""
