"""Database session management.

Provides a single async engine + session factory shared across the app.
FastAPI uses `get_session()` as a dependency; the cron pipeline uses
`session_scope()` as a context manager.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from elise_leads.settings import get_settings

# ----------------------------------------------------------------------------
# Engine + session factory (module-level singletons)
# ----------------------------------------------------------------------------

_settings = get_settings()


def _create_engine() -> AsyncEngine:
    """Create the async engine.

    SQLite needs `connect_args={"check_same_thread": False}` and uses NullPool
    for simplicity. Postgres uses default pooling.
    """
    kwargs: dict = {"echo": False, "future": True}

    if _settings.is_sqlite:
        # SQLite-specific tuning: allow cross-coroutine usage
        kwargs["connect_args"] = {"check_same_thread": False}

    return create_async_engine(_settings.database_url, **kwargs)


engine: AsyncEngine = _create_engine()

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


# ----------------------------------------------------------------------------
# Context managers / dependencies
# ----------------------------------------------------------------------------


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Async context manager for a DB session with automatic commit/rollback.

    Usage:
        async with session_scope() as session:
            session.add(obj)
            # commits on exit; rolls back on exception
    """
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error.

    Usage in a route:
        @router.get("/leads/{lead_id}")
        async def get_lead(lead_id: UUID, session: AsyncSession = Depends(get_session)):
            ...
    """
    async with session_scope() as session:
        yield session
