"""Lead — a single inbound prospect record.

The 7 input fields from the PDF Context section, plus lifecycle tracking.
After a Run processes a lead, it accumulates EnrichedData / Score / Email
relationships for downstream display in the dashboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base, utcnow

if TYPE_CHECKING:
    from elise_leads.models.api_log import ApiLog
    from elise_leads.models.email import Email
    from elise_leads.models.enriched import EnrichedData
    from elise_leads.models.provenance import Provenance
    from elise_leads.models.run import Run
    from elise_leads.models.score import Score


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ------------------------------------------------------------------
    # Input fields (PDF Context section, 7 fields)
    # ------------------------------------------------------------------
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    property_address: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(50), nullable=False, default="US")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    # 'pending' | 'processing' | 'processed' | 'failed'
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    run: Mapped["Run | None"] = relationship(back_populates="leads")
    enriched: Mapped["EnrichedData | None"] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )
    score: Mapped["Score | None"] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )
    # NOTE: relationship is `email_draft` (not `email`) to avoid collision
    # with the `email` column above (the contact's email address).
    email_draft: Mapped["Email | None"] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )
    provenance_records: Mapped[list["Provenance"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    api_logs: Mapped[list["ApiLog"]] = relationship(back_populates="lead")

    # Useful composite index for dashboard "pending/recent" queries
    __table_args__ = (
        Index("ix_leads_status_uploaded", "status", "uploaded_at"),
    )

    def __repr__(self) -> str:
        return f"<Lead id={self.id} email={self.email} status={self.status}>"
