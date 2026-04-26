"""Shared pytest fixtures.

Provides:
- An in-memory SQLite engine per test session
- An async session fixture (function-scoped) that creates/drops all tables
  around each test for isolation

Tests can override settings via env vars (e.g., DATABASE_URL=...) or by
clearing the get_settings cache.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Force in-memory SQLite for all tests
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from elise_leads.models import Base  # noqa: E402  (import after env var)
from elise_leads.settings import get_settings  # noqa: E402


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default policy. Override here if you need a custom one."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Create a fresh in-memory SQLite engine for each test."""
    # Clear settings cache so DATABASE_URL env var is picked up fresh
    get_settings.cache_clear()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables and dispose
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Provide an async DB session bound to the test engine."""
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
