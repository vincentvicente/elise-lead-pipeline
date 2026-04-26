"""/api/v1/leads — list with filters + full detail with provenance."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from elise_leads.api.deps import get_session
from elise_leads.api.schemas.lead import (
    EmailOut,
    FeedbackHistoryItem,
    LeadDetail,
    LeadListItem,
    LeadListResponse,
    ProvenanceFactOut,
    ScoreOut,
)
from elise_leads.generation.insights import extract as extract_insights
from elise_leads.models import (
    Email,
    EnrichedData,
    Feedback,
    Lead,
    Provenance,
    Score,
)

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=LeadListResponse, summary="List leads with filters")
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tier: str | None = Query(default=None, description="Hot | Warm | Cold"),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="pending | processing | processed | failed",
    ),
    run_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> LeadListResponse:
    """Returns Lead rows joined with Score + Email summary fields.

    Used by the dashboard /leads (Table view) and /inbox (Inbox/Card view).
    """
    base_q = (
        select(Lead, Score.total, Score.tier, Email.source)
        .outerjoin(Score, Score.lead_id == Lead.id)
        .outerjoin(Email, Email.lead_id == Lead.id)
    )
    count_q = select(func.count(Lead.id))
    if status_filter:
        base_q = base_q.where(Lead.status == status_filter)
        count_q = count_q.where(Lead.status == status_filter)
    if run_id is not None:
        base_q = base_q.where(Lead.run_id == run_id)
        count_q = count_q.where(Lead.run_id == run_id)
    if tier:
        # Tier filter requires a join, so only valid against scored leads
        base_q = base_q.where(Score.tier == tier)
        count_q = count_q.join(Score, Score.lead_id == Lead.id).where(Score.tier == tier)

    total = (await session.execute(count_q)).scalar_one()

    rows = (
        await session.execute(
            base_q.order_by(desc(Lead.uploaded_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items: list[LeadListItem] = []
    for lead, score_total, score_tier, email_source in rows:
        items.append(
            LeadListItem(
                id=lead.id,
                name=lead.name,
                email=lead.email,
                company=lead.company,
                city=lead.city,
                state=lead.state,
                country=lead.country,
                status=lead.status,
                uploaded_at=lead.uploaded_at,
                processed_at=lead.processed_at,
                score_total=score_total,
                score_tier=score_tier,
                email_source=email_source,
            )
        )

    return LeadListResponse(leads=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{lead_id}",
    response_model=LeadDetail,
    summary="Full lead detail with provenance + feedback history",
)
async def get_lead(
    lead_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> LeadDetail:
    """Loads everything needed for /leads/:id + /inbox card mode.

    Insights are computed on the fly from the score + enriched payload — they
    aren't persisted (rule-based, deterministic, free).
    """
    lead = (
        await session.execute(
            select(Lead)
            .where(Lead.id == lead_id)
            .options(
                selectinload(Lead.enriched),
                selectinload(Lead.score),
                selectinload(Lead.email_draft),
                selectinload(Lead.provenance_records),
            )
        )
    ).scalar_one_or_none()

    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Lead not found")

    # Feedback history for this lead's email
    feedback_rows: list[Feedback] = []
    if lead.email_draft is not None:
        feedback_rows = (
            await session.execute(
                select(Feedback)
                .where(Feedback.email_id == lead.email_draft.id)
                .order_by(Feedback.created_at)
            )
        ).scalars().all()

    # Build response
    enriched_payload = _enriched_to_dict(lead.enriched)
    insights: list[str] = []
    if lead.score is not None:
        insights = extract_insights(
            lead_company=lead.company,
            nmhc=enriched_payload.get("nmhc"),
            wiki=enriched_payload.get("wiki"),
            news=enriched_payload.get("news"),
            census=enriched_payload.get("census"),
            walkscore=enriched_payload.get("walkscore"),
            fred=enriched_payload.get("fred"),
            score_tier=lead.score.tier,
            score_total=lead.score.total,
        )

    return LeadDetail(
        id=lead.id,
        run_id=lead.run_id,
        name=lead.name,
        email=lead.email,
        company=lead.company,
        property_address=lead.property_address,
        city=lead.city,
        state=lead.state,
        country=lead.country,
        status=lead.status,
        uploaded_at=lead.uploaded_at,
        processed_at=lead.processed_at,
        error_message=lead.error_message,
        insights=insights,
        enriched=enriched_payload,
        provenance=[
            ProvenanceFactOut(
                fact_key=p.fact_key,
                fact_value=p.fact_value,
                source=p.source,
                confidence=p.confidence,
                fetched_at=p.fetched_at,
            )
            for p in lead.provenance_records
        ],
        score=(
            ScoreOut(
                total=lead.score.total,
                tier=lead.score.tier,
                breakdown=lead.score.breakdown,
                reasons=lead.score.reasons,
            )
            if lead.score is not None
            else None
        ),
        email_draft=(
            EmailOut(
                id=lead.email_draft.id,
                subject=lead.email_draft.subject,
                body=lead.email_draft.body,
                source=lead.email_draft.source,
                proof_point_used=lead.email_draft.proof_point_used,
                warnings=lead.email_draft.warnings,
                hallucination_check=lead.email_draft.hallucination_check,
                created_at=lead.email_draft.created_at,
            )
            if lead.email_draft is not None
            else None
        ),
        feedback=[
            FeedbackHistoryItem(
                id=f.id,
                sdr_email=f.sdr_email,
                action=f.action,
                final_subject=f.final_subject,
                final_body=f.final_body,
                rejection_reason=f.rejection_reason,
                review_seconds=f.review_seconds,
                created_at=f.created_at,
            )
            for f in feedback_rows
        ],
    )


def _enriched_to_dict(enriched: EnrichedData | None) -> dict:
    if enriched is None:
        return {}
    return {
        "nmhc": enriched.nmhc_json,
        "wiki": enriched.wiki_json,
        "news": enriched.news_json,
        "walkscore": enriched.walkscore_json,
        "fred": enriched.fred_json,
        "census": enriched.census_json,
        "errors": enriched.errors or {},
    }
