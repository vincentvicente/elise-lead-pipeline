"""Feedback — SDR action on an email draft (the Phase 2 data goldmine).

Many-to-one with Email. Each row captures one SDR decision:
- 'approved' — sent as-is
- 'edited'   — final_subject/body store the changes; diff computed at query time
- 'rejected' — rejection_reason recorded

`review_seconds` is the **verification burden metric** — directly powers
the rollout-plan KPI ("median review time < 2 min/email") and the dashboard
overview chart.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base, utcnow

if TYPE_CHECKING:
    from elise_leads.models.email import Email


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )

    sdr_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    # 'approved' | 'edited' | 'rejected'
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Edit fields — populated only when action='edited'
    final_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    final_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Reject field — populated only when action='rejected'
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The verification-burden metric (seconds from opening detail view to action)
    review_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    email: Mapped["Email"] = relationship(back_populates="feedback")

    __table_args__ = (
        CheckConstraint(
            "action IN ('approved', 'edited', 'rejected')",
            name="action_enum",
        ),
        CheckConstraint("review_seconds >= 0", name="review_seconds_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} email_id={self.email_id} action={self.action}>"
