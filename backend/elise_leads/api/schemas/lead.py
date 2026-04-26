"""Lead-related response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LeadListItem(BaseModel):
    """Compact lead row for list/table views."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    company: str
    city: str
    state: str
    country: str
    status: str
    uploaded_at: datetime
    processed_at: datetime | None = None
    # Joined from the score table for the table view
    score_total: int | None = None
    score_tier: str | None = None
    # Joined from the email table
    email_source: str | None = None


class LeadListResponse(BaseModel):
    leads: list[LeadListItem]
    total: int
    page: int
    page_size: int


class ProvenanceFactOut(BaseModel):
    fact_key: str
    fact_value: Any
    source: str
    confidence: float
    fetched_at: datetime


class ScoreOut(BaseModel):
    total: int
    tier: str
    breakdown: dict[str, int]
    reasons: list[str]


class EmailOut(BaseModel):
    id: uuid.UUID
    subject: str
    body: str
    source: str
    proof_point_used: str | None = None
    warnings: list[str]
    hallucination_check: dict[str, Any]
    created_at: datetime


class FeedbackHistoryItem(BaseModel):
    id: uuid.UUID
    sdr_email: str
    action: str
    final_subject: str | None = None
    final_body: str | None = None
    rejection_reason: str | None = None
    review_seconds: int
    created_at: datetime


class LeadDetail(BaseModel):
    """Full detail for the dashboard /leads/:id page."""

    # Core lead fields
    id: uuid.UUID
    run_id: uuid.UUID | None = None
    name: str
    email: str
    company: str
    property_address: str
    city: str
    state: str
    country: str
    status: str
    uploaded_at: datetime
    processed_at: datetime | None = None
    error_message: str | None = None

    # Computed insights (rules-based, derived at request time)
    insights: list[str] = Field(default_factory=list)

    # Related data — `email_draft` (not `email`) to avoid colliding with the
    # contact-email field above. Mirrors the model rename from M1.
    enriched: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceFactOut] = Field(default_factory=list)
    score: ScoreOut | None = None
    email_draft: EmailOut | None = None
    feedback: list[FeedbackHistoryItem] = Field(default_factory=list)
