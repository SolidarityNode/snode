"""Database wiring: SQLAlchemy engine, sessions and declarative base (PostgreSQL/PostGIS).

Large datasets live in Parquet files; the database holds metadata and result indexes
(AGENTS.md, ADR 0008). No tables exist yet.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from solidaritynode_backend.config import get_settings

__all__ = ["Base", "check_database", "get_engine", "get_session"]


class Base(DeclarativeBase):
    """Declarative base for ORM models (Alembic target metadata)."""


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide engine built from settings (connects lazily)."""
    url = get_settings().database_url.get_secret_value()
    return create_engine(url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """Yield a session for one request (FastAPI dependency)."""
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        yield session


def check_database(engine: Engine) -> bool:
    """Return whether ``SELECT 1`` succeeds on ``engine``."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
