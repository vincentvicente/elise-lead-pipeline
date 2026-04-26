"""EnrichedData — raw API responses keyed by lead.

One-to-one with Lead. Each enrichment source stores its full JSON response,
allowing post-hoc re-scoring without re-fetching, plus auditing of what the
API actually returned.

Also stores a per-source `errors` map ("which APIs failed and why") so the
scoring engine can apply median fallbacks transparently.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base, utcnow

if TYPE_CHECKING:
    from elise_leads.models.lead import Lead


class EnrichedData(Base):
    __tablename__ = "enriched_data"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )

    # ------------------------------------------------------------------
    # Per-source raw payloads
    # ------------------------------------------------------------------
    census_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    news_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    wiki_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    walkscore_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    fred_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    nmhc_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # ------------------------------------------------------------------
    # Per-source error map: {"newsapi": "rate_limit_exceeded", ...}
    # ------------------------------------------------------------------
    errors: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    lead: Mapped["Lead"] = relationship(back_populates="enriched")

    def __repr__(self) -> str:
        return f"<EnrichedData lead_id={self.lead_id}>"
