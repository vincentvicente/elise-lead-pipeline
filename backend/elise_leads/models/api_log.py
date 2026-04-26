"""ApiLog — one row per external API call.

Powers:
- Dashboard `/runs/:id` API performance table (avg / p95 / failures by source)
- Dashboard `/metrics/api-performance` historical trends
- Provenance.raw_ref audit pointer

Note BigInt PK because this table grows fastest of all (50 leads × ~6 API
calls each = 300 rows per run; 1 year of daily runs = ~110k rows).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base

if TYPE_CHECKING:
    from elise_leads.models.lead import Lead
    from elise_leads.models.run import Run


# BigInteger autoincrement is unsupported on SQLite; use plain Integer there
_BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class ApiLog(Base):
    __tablename__ = "api_logs"

    id: Mapped[int] = mapped_column(_BigIntPK, primary_key=True, autoincrement=True)

    run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 'census_geocoder' | 'census_acs' | 'newsapi' | 'wikipedia'
    # | 'walkscore' | 'fred' | 'nmhc' | 'claude_sonnet' | 'claude_haiku'
    api_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)

    # 'timeout' | 'rate_limit' | 'http_5xx' | 'http_4xx' | 'parse_error' | None
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    run: Mapped["Run | None"] = relationship(back_populates="api_logs")
    lead: Mapped["Lead | None"] = relationship(back_populates="api_logs")

    __table_args__ = (
        # Helps "API performance over time" queries
        Index("ix_api_logs_api_started", "api_name", "started_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ApiLog id={self.id} api={self.api_name} "
            f"success={self.success} ms={self.duration_ms}>"
        )
