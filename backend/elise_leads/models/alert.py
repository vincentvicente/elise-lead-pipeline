"""AlertHistory — dedup state for the alerting system.

Single row per `alert_key` (e.g., "pipeline_crash", "high_failure_rate").
Stores `last_sent` so the alerting client can apply cooldown:
- 'immediate' severity → cooldown 0 (always sends)
- 'throttled' severity → cooldown 1h (suppresses duplicates)

Without this, a tight retry loop would spam the SDR's inbox.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from elise_leads.models.base import Base, utcnow


class AlertHistory(Base):
    __tablename__ = "alert_history"

    # The dedup key (e.g., "pipeline_crash" / "newsapi_quota_exhausted")
    alert_key: Mapped[str] = mapped_column(String(100), primary_key=True)

    # 'immediate' | 'throttled'
    severity: Mapped[str] = mapped_column(String(20), nullable=False)

    last_sent: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # How many times this alert has fired (since project start)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<AlertHistory key={self.alert_key} severity={self.severity} "
            f"count={self.count}>"
        )
