"""Score — output of the rule-based scoring engine.

One-to-one with Lead. Stores:
- total (0–100)
- tier (Hot/Warm/Cold)
- breakdown (per-dimension scores for explainability)
- reasons (plain-English bullets shown in dashboard)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base, utcnow

if TYPE_CHECKING:
    from elise_leads.models.lead import Lead


class Score(Base):
    __tablename__ = "scores"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )

    total: Mapped[int] = mapped_column(Integer, nullable=False)

    # 'Hot' | 'Warm' | 'Cold'
    tier: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Per-dimension breakdown:
    # {"company_scale": 25, "buy_intent": 20, "vertical_fit": 10,
    #  "market_fit": 11, "property_fit": 9, "market_dynamics": 2,
    #  "contact_fit": 15}
    breakdown: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Plain-English bullet reasons shown to SDRs in dashboard
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    lead: Mapped["Lead"] = relationship(back_populates="score")

    __table_args__ = (
        CheckConstraint("total >= 0 AND total <= 100", name="total_in_range"),
        CheckConstraint("tier IN ('Hot', 'Warm', 'Cold')", name="tier_enum"),
    )

    def __repr__(self) -> str:
        return f"<Score lead_id={self.lead_id} total={self.total} tier={self.tier}>"
