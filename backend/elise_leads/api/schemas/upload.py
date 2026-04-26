"""CSV upload response schema."""

from __future__ import annotations

from pydantic import BaseModel


class UploadRowError(BaseModel):
    row_number: int
    error: str


class UploadResponse(BaseModel):
    """POST /api/v1/uploads response."""

    uploaded: int  # number of rows accepted into pending state
    skipped: int   # rows rejected (validation errors)
    errors: list[UploadRowError] = []
