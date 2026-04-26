"""Shared FastAPI dependencies.

Mostly thin re-exports of the DB session helper so routers stay clean.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.db import session_scope


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a per-request DB session.

    Identical to elise_leads.db.get_session — re-exported here so routers
    have a stable import path under the api/ package.
    """
    async with session_scope() as session:
        yield session
