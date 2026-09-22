"""Database engine, session factory, and declarative base.

The engine is created lazily: importing models must not require a live database
driver or connection. This keeps model imports cheap for tests and tooling, and
makes the app fail at connect time (recoverable, observable) rather than at
import time (crash on startup).
"""
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


@lru_cache
def get_engine() -> Engine:
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def SessionLocal() -> Session:  # noqa: N802 - factory-style callable, kept for call sites
    """Create a new session bound to the lazily-built engine."""
    return get_session_factory()()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session (unit of work).

    The session commits when the request handler returns and rolls back if it
    raises. Without that commit, ``close()`` discards the transaction: every
    write endpoint returned 2xx while persisting nothing, because the OMS
    services only ``flush()`` (which makes rows visible to the current session,
    so the in-session tests still passed) and never commit themselves.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
