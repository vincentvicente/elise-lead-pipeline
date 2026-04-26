"""POST /api/v1/leads/{lead_id}/feedback — one-click approve/edit/reject.

This endpoint backs the dashboard's Inbox + Card review flows. Each call
appends a row to the `feedback` table (multiple feedbacks per email is
fine — captures revisions over time).

`review_seconds` is the rollout-plan KPI ("verification burden"): the
number of seconds between the SDR opening the lead detail view and
clicking Approve/Edit/Reject. The frontend measures this and sends it
in the request.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.api.deps import get_session
from elise_leads.api.schemas.feedback import FeedbackCreate, FeedbackOut
from elise_leads.models import Email, Feedback, Lead

router = APIRouter(prefix="/leads", tags=["feedback"])


@router.post(
    "/{lead_id}/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit SDR feedback (approve / edit / reject)",
)
async def submit_feedback(
    lead_id: uuid.UUID,
    payload: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
) -> FeedbackOut:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lead not found")

    # Explicit query — async sessions can't lazy-load relationships safely
    email = (
        await session.execute(select(Email).where(Email.lead_id == lead_id))
    ).scalar_one_or_none()

    if email is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Lead has no email draft yet — process the lead first",
        )

    feedback = Feedback(
        email_id=email.id,
        sdr_email=str(payload.sdr_email),
        action=payload.action,
        final_subject=payload.final_subject,
        final_body=payload.final_body,
        rejection_reason=payload.rejection_reason,
        review_seconds=payload.review_seconds,
    )
    session.add(feedback)
    await session.flush()
    return FeedbackOut.model_validate(feedback)
