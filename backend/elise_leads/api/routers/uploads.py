"""POST /api/v1/uploads — CSV upload → pending leads.

Validates each row against the 7 PDF Context fields and inserts as
pending leads. Failed rows are reported back so the SDR can fix and
re-upload.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.api.deps import get_session
from elise_leads.api.schemas.upload import UploadResponse, UploadRowError
from elise_leads.models import Lead

router = APIRouter(prefix="/uploads", tags=["uploads"])

REQUIRED_COLUMNS = (
    "name",
    "email",
    "company",
    "property_address",
    "city",
    "state",
    "country",
)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB cap


class _LeadRow(BaseModel):
    """Per-row CSV validator — mirrors the 7 input fields."""

    name: str
    email: EmailStr
    company: str
    property_address: str
    city: str
    state: str
    country: str = "US"


@router.post(
    "",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload CSV of leads",
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV with columns: " + ", ".join(REQUIRED_COLUMNS)),
    session: AsyncSession = Depends(get_session),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .csv",
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB cap",
        )

    try:
        text = raw.decode("utf-8-sig")  # tolerate BOM from Excel exports
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded",
        )

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV has no header row",
        )

    missing = set(REQUIRED_COLUMNS) - {c.strip() for c in reader.fieldnames}
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns: {sorted(missing)}",
        )

    accepted = 0
    skipped = 0
    errors: list[UploadRowError] = []

    for idx, raw_row in enumerate(reader, start=2):  # row 1 is header
        cleaned = {k.strip(): (v or "").strip() for k, v in raw_row.items()}
        try:
            row = _LeadRow(**{k: cleaned.get(k, "") for k in REQUIRED_COLUMNS})
        except ValidationError as e:
            skipped += 1
            errors.append(
                UploadRowError(
                    row_number=idx,
                    error="; ".join(
                        f"{'.'.join(map(str, err['loc']))}: {err['msg']}"
                        for err in e.errors()
                    ),
                )
            )
            continue

        session.add(
            Lead(
                name=row.name,
                email=row.email,
                company=row.company,
                property_address=row.property_address,
                city=row.city,
                state=row.state,
                country=row.country,
                status="pending",
            )
        )
        accepted += 1

    return UploadResponse(uploaded=accepted, skipped=skipped, errors=errors)
