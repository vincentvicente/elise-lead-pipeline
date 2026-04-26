"""Feedback request/response schemas — the Phase 2 data goldmine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

FeedbackAction = Literal["approved", "edited", "rejected"]


class FeedbackCreate(BaseModel):
    """POST /api/v1/leads/{lead_id}/feedback body."""

    sdr_email: EmailStr
    action: FeedbackAction

    # Required when action='edited'
    final_subject: str | None = Field(default=None, max_length=500)
    final_body: str | None = None

    # Required when action='rejected'
    rejection_reason: str | None = None

    # Mandatory verification-burden metric (powers the rollout-plan KPI)
    review_seconds: int = Field(ge=0, le=86_400)

    @model_validator(mode="after")
    def _check_action_payload(self) -> "FeedbackCreate":
        if self.action == "edited" and not (self.final_subject and self.final_body):
            raise ValueError(
                "final_subject + final_body required when action='edited'"
            )
        if self.action == "rejected" and not self.rejection_reason:
            raise ValueError("rejection_reason required when action='rejected'")
        return self


class FeedbackOut(BaseModel):
    """Persisted feedback row returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email_id: uuid.UUID
    sdr_email: str
    action: str
    final_subject: str | None = None
    final_body: str | None = None
    rejection_reason: str | None = None
    review_seconds: int
    created_at: datetime
