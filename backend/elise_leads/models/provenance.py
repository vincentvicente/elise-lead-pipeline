"""Provenance — fact-level data lineage for hallucination defense.

Every fact that goes into the LLM prompt is recorded here with:
- source (which API, which date)
- confidence (0.0–1.0; LLM only cites specific numbers when ≥0.85)
- raw_ref (link back to api_logs.id for full audit)

This is the foundation of Layer 1 of the hallucination defense system
(see PART_A §11.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base, utcnow

if TYPE_CHECKING:
    from elise_leads.models.lead import Lead


class Provenance(Base):
    __tablename__ = "provenance"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )

    # Stable key naming the fact (e.g., "renter_pct", "company_units_managed")
    fact_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # The actual fact value (string / number / object)
    fact_value: Mapped[Any] = mapped_column(JSON, nullable=False)

    # Source identifier (e.g., "census_acs_2022", "newsapi_2026-04-22")
    source: Mapped[str] = mapped_column(String(100), nullable=False)

    # 0.0–1.0; LLM prompt restricts specific-number citations to ≥0.85
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Optional FK string to api_logs.id for full audit trail
    raw_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="provenance_records")

    __table_args__ = (
        Index("ix_provenance_lead_key", "lead_id", "fact_key"),
    )

    def __repr__(self) -> str:
        return f"<Provenance lead_id={self.lead_id} {self.fact_key}={self.fact_value} ({self.source})>"
