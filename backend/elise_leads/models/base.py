"""Declarative base for all SQLAlchemy models.

Centralizes:
- Naming conventions (avoids Alembic auto-naming issues)
- Common timestamp mixins
- UUID type that works on both Postgres (native UUID) and SQLite (CHAR(36))
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import CHAR, DateTime, MetaData, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ----------------------------------------------------------------------------
# Naming convention — keeps Alembic-generated constraint names stable
# ----------------------------------------------------------------------------
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide declarative base."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ----------------------------------------------------------------------------
# Cross-database UUID type
# ----------------------------------------------------------------------------
class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses Postgres native UUID when available; falls back to CHAR(36) on SQLite.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgresUUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value) if not isinstance(value, uuid.UUID) else value
        return str(value) if isinstance(value, uuid.UUID) else value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


# ----------------------------------------------------------------------------
# Timestamp helpers
# ----------------------------------------------------------------------------
def utcnow() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Adds created_at to a model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
