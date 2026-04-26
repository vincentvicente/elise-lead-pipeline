"""Run — one execution of the cron pipeline.

A Run represents one batch processing of pending leads. Captures:
- Start/end times and final status
- Aggregate counts (total, success, failure)
- Auto-generated MD report rendered in dashboard /runs/:id
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base, utcnow

if TYPE_CHECKING:
    from elise_leads.models.api_log import ApiLog
    from elise_leads.models.lead import Lead


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 'running' | 'success' | 'partial' | 'crashed'
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)

    lead_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # MD report rendered in dashboard
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    leads: Mapped[list["Lead"]] = relationship(back_populates="run")
    api_logs: Mapped[list["ApiLog"]] = relationship(back_populates="run")

    def __repr__(self) -> str:
        return f"<Run id={self.id} status={self.status} leads={self.lead_count}>"
