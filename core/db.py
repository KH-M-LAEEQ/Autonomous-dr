"""SQLAlchemy engine and session factory for Postgres."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            future=True,
            connect_args={"connect_timeout": 2},
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction boundary. Commit on success, roll back on any exception."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping() -> bool:
    """True if Postgres answers. Used by /health."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
