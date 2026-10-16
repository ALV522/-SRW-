from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _enable_sqlite_guards(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def create_v1_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_guards)
    return engine


def create_v1_session_factory(bind: Engine) -> sessionmaker[Session]:
    if not isinstance(bind, Engine):
        raise TypeError("create_v1_session_factory requires an explicit SQLAlchemy Engine")
    return sessionmaker(bind=bind, autoflush=False, expire_on_commit=False)


@contextmanager
def v1_session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
