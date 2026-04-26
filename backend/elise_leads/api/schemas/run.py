"""Run-related response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunListItem(BaseModel):
    """Compact row for the /runs history page."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    lead_count: int
    success_count: int
    failure_count: int


class RunListResponse(BaseModel):
    runs: list[RunListItem]
    total: int
    page: int
    page_size: int


class RunDetail(BaseModel):
    """Full detail for /runs/:id including the rendered MD report."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    lead_count: int
    success_count: int
    failure_count: int
    report_md: str | None = None


class RunTriggerResponse(BaseModel):
    """Response for POST /runs/trigger — pipeline started in background."""

    run_id: uuid.UUID
    status: str = "queued"
    message: str = "Pipeline scheduled. Poll GET /api/v1/runs/{run_id} for progress."
