"""Alembic migration environment.

Reads DATABASE_URL from elise_leads.settings (NOT alembic.ini),
so dev/staging/prod all use the same env-driven config.

Supports both sync (offline mode) and async (online mode) execution.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import models so Alembic autogenerate sees the metadata
from elise_leads.models import Base
from elise_leads.settings import get_settings

# Alembic Config object — gives access to .ini values
config = context.config

# Inject DATABASE_URL from settings (overrides alembic.ini)
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


# ----------------------------------------------------------------------------
# Offline mode: emit SQL without DB connection
# ----------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures context with just a URL, not an Engine, and emits SQL to stdout.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=settings.is_sqlite,  # SQLite needs batch mode for ALTER
    )

    with context.begin_transaction():
        context.run_migrations()


# ----------------------------------------------------------------------------
# Online mode: connect to DB and run migrations
# ----------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=settings.is_sqlite,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine, run migrations, dispose."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode (uses async engine)."""
    asyncio.run(run_async_migrations())


# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
