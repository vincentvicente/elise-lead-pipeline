"""Smoke tests for M1 — verifies all 9 models can be created and persisted.

These are intentionally minimal: just checks that:
- Schema creation succeeds
- Round-tripping through SQLAlchemy works
- Relationships are configured correctly

Real business logic tests come in M2+ once we have actual code to test.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.models import (
    AlertHistory,
    ApiLog,
    Email,
    EnrichedData,
    Feedback,
    Lead,
    Provenance,
    Run,
    Score,
)


@pytest.mark.asyncio
async def test_run_create_and_query(session: AsyncSession) -> None:
    run = Run(status="success", lead_count=10, success_count=10)
    session.add(run)
    await session.commit()

    result = await session.execute(select(Run).where(Run.id == run.id))
    fetched = result.scalar_one()
    assert fetched.status == "success"
    assert fetched.lead_count == 10
    assert fetched.id == run.id


@pytest.mark.asyncio
async def test_lead_with_full_lifecycle(session: AsyncSession) -> None:
    """Persist a Lead with all 7 input fields, then attach Enriched/Score/Email."""
    run = Run(status="success", lead_count=1, success_count=1)
    session.add(run)
    await session.flush()

    lead = Lead(
        run_id=run.id,
        name="Sarah Johnson",
        email="sarah.johnson@greystar.com",
        company="Greystar",
        property_address="123 Main St",
        city="Austin",
        state="TX",
        country="US",
        status="processed",
        processed_at=datetime.now(timezone.utc),
    )
    session.add(lead)
    await session.flush()

    # Attach EnrichedData
    enriched = EnrichedData(
        lead_id=lead.id,
        census_json={"renter_pct": 0.68, "median_income": 72000},
        news_json={"articles": []},
        errors={},
    )
    session.add(enriched)

    # Attach Score
    score = Score(
        lead_id=lead.id,
        total=92,
        tier="Hot",
        breakdown={"company_scale": 25, "buy_intent": 20, "vertical_fit": 10},
        reasons=["NMHC #1 operator", "M&A news"],
    )
    session.add(score)

    # Attach Email
    email = Email(
        lead_id=lead.id,
        subject="Quick question about Greystar",
        body="Hi Sarah,\n\nSaw the Alliance acquisition...",
        source="llm:claude-sonnet-4-6",
        warnings=[],
        hallucination_check={"passed": True, "issues": []},
        proof_point_used="equity_residential",
    )
    session.add(email)

    await session.commit()

    # Refresh and verify relationships
    await session.refresh(lead, ["enriched", "score", "email_draft"])
    assert lead.enriched is not None
    assert lead.enriched.census_json["renter_pct"] == 0.68
    assert lead.score is not None
    assert lead.score.tier == "Hot"
    assert lead.email_draft is not None
    assert lead.email_draft.source == "llm:claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_provenance_record(session: AsyncSession) -> None:
    """Provenance stores per-fact source + confidence."""
    lead = Lead(
        name="Mike Lee",
        email="mike@assetliving.com",
        company="Asset Living",
        property_address="456 Oak Ave",
        city="Houston",
        state="TX",
        country="US",
    )
    session.add(lead)
    await session.flush()

    prov = Provenance(
        lead_id=lead.id,
        fact_key="renter_pct",
        fact_value=0.68,
        source="census_acs_2022",
        confidence=0.95,
        fetched_at=datetime.now(timezone.utc),
        raw_ref=None,
    )
    session.add(prov)
    await session.commit()

    result = await session.execute(
        select(Provenance).where(Provenance.lead_id == lead.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].confidence == 0.95
    assert rows[0].source == "census_acs_2022"


@pytest.mark.asyncio
async def test_feedback_records_review_seconds(session: AsyncSession) -> None:
    """Feedback captures the verification-burden metric."""
    lead = Lead(
        name="Test", email="t@example.com", company="Test Co",
        property_address="123", city="Boston", state="MA", country="US",
    )
    session.add(lead)
    await session.flush()

    email = Email(
        lead_id=lead.id, subject="Hi", body="Hello",
        source="llm:claude-sonnet-4-6", warnings=[], hallucination_check={},
    )
    session.add(email)
    await session.flush()

    feedback = Feedback(
        email_id=email.id,
        sdr_email="sdr@elise.ai",
        action="approved",
        review_seconds=45,
    )
    session.add(feedback)
    await session.commit()

    result = await session.execute(
        select(Feedback).where(Feedback.email_id == email.id)
    )
    fb = result.scalar_one()
    assert fb.action == "approved"
    assert fb.review_seconds == 45


@pytest.mark.asyncio
async def test_api_log_and_alert_history(session: AsyncSession) -> None:
    """ApiLog and AlertHistory are independent / appendable."""
    log = ApiLog(
        api_name="newsapi",
        started_at=datetime.now(timezone.utc),
        duration_ms=234,
        http_status=200,
        success=True,
    )
    session.add(log)

    alert = AlertHistory(
        alert_key="pipeline_crash",
        severity="immediate",
        last_sent=datetime.now(timezone.utc),
        count=1,
    )
    session.add(alert)
    await session.commit()

    log_result = await session.execute(select(ApiLog))
    assert len(log_result.scalars().all()) == 1

    alert_result = await session.execute(
        select(AlertHistory).where(AlertHistory.alert_key == "pipeline_crash")
    )
    fetched = alert_result.scalar_one()
    assert fetched.count == 1
    assert fetched.severity == "immediate"
