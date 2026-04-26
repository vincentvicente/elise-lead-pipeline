"""Email — generated outreach draft.

One-to-one with Lead. Records:
- subject + body (the draft)
- source: which fallback layer produced this email
   ("llm:claude-sonnet-4-6" / "llm:claude-haiku-4-5" / "template_fallback")
- warnings: validation issues (jargon, length, etc.) — does NOT block output
- hallucination_check: post-gen detection result
- proof_point_used: which proof point the rule-based selector chose
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from elise_leads.models.base import GUID, Base, utcnow

if TYPE_CHECKING:
    from elise_leads.models.feedback import Feedback
    from elise_leads.models.lead import Lead


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Generated content
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Where this draft came from in the fallback chain
    # 'llm:claude-sonnet-4-6' | 'llm:claude-haiku-4-5' | 'template_fallback'
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    # Non-blocking validation warnings (length, jargon, missing placeholder, etc.)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Post-gen hallucination detection result:
    # {"passed": True, "issues": [], "regenerations": 0}
    hallucination_check: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Which proof point the rule-based selector matched (e.g., "equity_residential")
    proof_point_used: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="email_draft")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="email", cascade="all")

    def __repr__(self) -> str:
        return f"<Email id={self.id} lead_id={self.lead_id} source={self.source}>"
