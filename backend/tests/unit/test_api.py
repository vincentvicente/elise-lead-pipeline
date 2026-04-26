"""HTTP integration tests for the FastAPI app.

Spins the FastAPI app against an in-memory SQLite engine, exercises each
endpoint end-to-end, and verifies status codes + response shapes.

Avoids hitting external APIs by short-circuiting where needed (e.g.
trigger endpoint validated for queueing only, not full execution).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timezone

# Ensure settings load with permissive defaults
os.environ.setdefault("CENSUS_API_KEY", "test")
os.environ.setdefault("NEWS_API_KEY", "test")
os.environ.setdefault("WALKSCORE_API_KEY", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("RESEND_API_KEY", "test")
os.environ.setdefault("ALERT_EMAIL", "alerts@example.com")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from elise_leads import db as db_mod
from elise_leads.api.main import create_app
from elise_leads.models import Email, EnrichedData, Feedback, Lead, Run, Score
from elise_leads.settings import get_settings


@pytest.fixture
def app(session):
    """Build a FastAPI app whose DB session uses the test in-memory engine."""
    get_settings.cache_clear()
    db_mod.SessionLocal = async_sessionmaker(
        bind=session.bind, expire_on_commit=False, autoflush=False
    )
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ============================================================================
# Health
# ============================================================================
@pytest.mark.asyncio
async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


# ============================================================================
# Uploads
# ============================================================================
@pytest.mark.asyncio
async def test_upload_csv_happy_path(client, session):
    csv_text = (
        "name,email,company,property_address,city,state,country\n"
        "Sarah Johnson,sarah@greystar.com,Greystar,123 Main St,Austin,TX,US\n"
        "Mike Lee,mike@assetliving.com,Asset Living,456 Oak Ave,Houston,TX,US\n"
    )
    files = {"file": ("leads.csv", io.BytesIO(csv_text.encode()), "text/csv")}

    r = await client.post("/api/v1/uploads", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["uploaded"] == 2
    assert body["skipped"] == 0
    assert body["errors"] == []

    # DB has 2 pending leads
    from sqlalchemy import select

    rows = (await session.execute(select(Lead))).scalars().all()
    assert len(rows) == 2
    assert all(lead.status == "pending" for lead in rows)


@pytest.mark.asyncio
async def test_upload_csv_rejects_missing_columns(client):
    bad_csv = "name,email\nA,a@b.com\n"
    files = {"file": ("bad.csv", io.BytesIO(bad_csv.encode()), "text/csv")}
    r = await client.post("/api/v1/uploads", files=files)
    assert r.status_code == 400
    assert "Missing required columns" in r.json()["detail"]


@pytest.mark.asyncio
async def test_upload_csv_partial_validation_errors(client):
    csv_text = (
        "name,email,company,property_address,city,state,country\n"
        "Good,sarah@greystar.com,Greystar,123 Main,Austin,TX,US\n"
        ",not-an-email,X,Y,Z,W,US\n"
    )
    files = {"file": ("mixed.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    r = await client.post("/api/v1/uploads", files=files)
    assert r.status_code == 201
    body = r.json()
    assert body["uploaded"] == 1
    assert body["skipped"] == 1
    assert len(body["errors"]) == 1


@pytest.mark.asyncio
async def test_upload_csv_rejects_non_csv_extension(client):
    files = {"file": ("not-a-csv.txt", io.BytesIO(b"x"), "text/plain")}
    r = await client.post("/api/v1/uploads", files=files)
    assert r.status_code == 400


# ============================================================================
# Runs
# ============================================================================
@pytest.mark.asyncio
async def test_list_runs_paginated(client, session):
    # Seed 3 runs
    for i in range(3):
        session.add(Run(status="success", lead_count=10, success_count=10))
    await session.commit()

    r = await client.get("/api/v1/runs?page_size=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["runs"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


@pytest.mark.asyncio
async def test_list_runs_status_filter(client, session):
    session.add(Run(status="success", lead_count=10, success_count=10))
    session.add(Run(status="crashed", lead_count=10))
    await session.commit()

    r = await client.get("/api/v1/runs?status=success")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["runs"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_get_run_404(client):
    r = await client.get(f"/api/v1/runs/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_run_returns_report_md(client, session):
    run = Run(status="success", lead_count=5, success_count=5, report_md="# Test")
    session.add(run)
    await session.commit()

    r = await client.get(f"/api/v1/runs/{run.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["report_md"] == "# Test"


# ============================================================================
# Leads
# ============================================================================
@pytest.mark.asyncio
async def test_list_leads_with_score_join(client, session):
    lead = Lead(
        name="A",
        email="a@b.com",
        company="X",
        property_address="1",
        city="C",
        state="TX",
        country="US",
        status="processed",
    )
    session.add(lead)
    await session.flush()
    session.add(
        Score(
            lead_id=lead.id,
            total=85,
            tier="Hot",
            breakdown={"company_scale": 25},
            reasons=["test"],
        )
    )
    await session.commit()

    r = await client.get("/api/v1/leads")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["leads"][0]
    assert item["score_total"] == 85
    assert item["score_tier"] == "Hot"


@pytest.mark.asyncio
async def test_get_lead_detail_404(client):
    r = await client.get(f"/api/v1/leads/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_lead_detail_with_full_relations(client, session):
    """Lead with all related rows → detail returns provenance + score + email."""
    lead = Lead(
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

    session.add(
        EnrichedData(
            lead_id=lead.id,
            nmhc_json={"matched": True, "rank": 1, "units_managed": 800_000},
            errors={},
        )
    )
    session.add(
        Score(
            lead_id=lead.id,
            total=92,
            tier="Hot",
            breakdown={"company_scale": 25, "buy_intent": 20},
            reasons=["NMHC #1"],
        )
    )
    email = Email(
        lead_id=lead.id,
        subject="Quick question",
        body="Hi Sarah,\n\nBest,\n[SDR Name]",
        source="llm:claude-sonnet-4-6",
        warnings=[],
        hallucination_check={"passed": True},
    )
    session.add(email)
    await session.commit()

    r = await client.get(f"/api/v1/leads/{lead.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(lead.id)
    assert body["score"]["total"] == 92
    assert body["email_draft"]["source"] == "llm:claude-sonnet-4-6"
    assert "Lead score: 92/100" in body["insights"][0]


# ============================================================================
# Feedback
# ============================================================================
async def _seed_lead_with_email(session) -> tuple[Lead, Email]:
    lead = Lead(
        name="X", email="x@y.com", company="Y", property_address="Z",
        city="A", state="B", country="US", status="processed",
    )
    session.add(lead)
    await session.flush()
    email = Email(
        lead_id=lead.id, subject="S", body="Hi,\n[SDR Name]",
        source="llm:claude-sonnet-4-6", warnings=[], hallucination_check={},
    )
    session.add(email)
    await session.commit()
    return lead, email


@pytest.mark.asyncio
async def test_submit_feedback_approved(client, session):
    lead, email = await _seed_lead_with_email(session)

    r = await client.post(
        f"/api/v1/leads/{lead.id}/feedback",
        json={
            "sdr_email": "sdr@elise.ai",
            "action": "approved",
            "review_seconds": 45,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["action"] == "approved"
    assert body["review_seconds"] == 45


@pytest.mark.asyncio
async def test_submit_feedback_edited_requires_final_fields(client, session):
    lead, _ = await _seed_lead_with_email(session)
    r = await client.post(
        f"/api/v1/leads/{lead.id}/feedback",
        json={
            "sdr_email": "sdr@elise.ai",
            "action": "edited",
            "review_seconds": 70,
            # missing final_subject + final_body
        },
    )
    assert r.status_code == 422  # pydantic rejection


@pytest.mark.asyncio
async def test_submit_feedback_rejected_requires_reason(client, session):
    lead, _ = await _seed_lead_with_email(session)
    r = await client.post(
        f"/api/v1/leads/{lead.id}/feedback",
        json={
            "sdr_email": "sdr@elise.ai",
            "action": "rejected",
            "review_seconds": 30,
            # missing rejection_reason
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback_no_email_yet(client, session):
    """Lead exists but email_draft doesn't — should 400."""
    lead = Lead(
        name="X", email="x@y.com", company="Y", property_address="Z",
        city="A", state="B", country="US", status="pending",
    )
    session.add(lead)
    await session.commit()
    r = await client.post(
        f"/api/v1/leads/{lead.id}/feedback",
        json={
            "sdr_email": "sdr@elise.ai",
            "action": "approved",
            "review_seconds": 10,
        },
    )
    assert r.status_code == 400


# ============================================================================
# Metrics
# ============================================================================
@pytest.mark.asyncio
async def test_metrics_overview_empty_db(client):
    """No data → endpoint still returns valid shape with zeroed KPIs."""
    r = await client.get("/api/v1/metrics/overview")
    assert r.status_code == 200
    body = r.json()
    assert "kpis" in body
    assert len(body["kpis"]) == 4
    assert body["tier_distribution"] == {"hot": 0, "warm": 0, "cold": 0}
    assert len(body["trend"]) == 7
    assert body["recent_runs"] == []


@pytest.mark.asyncio
async def test_metrics_overview_with_data(client, session):
    # Create one Hot processed lead with a Feedback row
    lead = Lead(
        name="X", email="x@y.com", company="Y", property_address="Z",
        city="A", state="B", country="US", status="processed",
        processed_at=datetime.now(timezone.utc),
    )
    session.add(lead)
    await session.flush()
    session.add(Score(lead_id=lead.id, total=85, tier="Hot", breakdown={}, reasons=[]))
    email = Email(
        lead_id=lead.id, subject="S", body="b",
        source="llm:claude-sonnet-4-6", warnings=[], hallucination_check={},
    )
    session.add(email)
    await session.flush()
    session.add(
        Feedback(
            email_id=email.id, sdr_email="s@e.ai", action="approved",
            review_seconds=60,
        )
    )
    await session.commit()

    r = await client.get("/api/v1/metrics/overview")
    assert r.status_code == 200
    body = r.json()
    # tier_distribution shows 1 Hot today
    assert body["tier_distribution"]["hot"] == 1
    # KPIs reflect 1 processed and 100% approval, 1 min review time
    kpis_by_label = {k["label"]: k["value"] for k in body["kpis"]}
    assert kpis_by_label["Processed today"] == 1
    assert kpis_by_label["Hot tier %"] == 100.0
    assert kpis_by_label["Approval rate"] == 100.0


@pytest.mark.asyncio
async def test_metrics_api_performance_empty(client):
    r = await client.get("/api/v1/metrics/api-performance")
    assert r.status_code == 200
    assert r.json() == []


# ============================================================================
# Webhooks (CRM inbound)
# ============================================================================
@pytest.mark.asyncio
async def test_webhook_inbound_creates_pending_lead(client, session):
    payload = {
        "contact_name": "Marcus Tate",
        "contact_email": "marcus.tate@rpmliving.com",
        "company": "RPM Living",
        "property_address": "555 Market Plaza",
        "city": "Austin",
        "state": "TX",
        "country": "US",
        "source": "salesforce_flow:inbound_demo_request",
        "external_id": "0034x0000",
    }
    r = await client.post("/api/v1/webhooks/inbound", json=payload)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "received"
    assert body["lead_id"]
    assert "next" in body["will_process"].lower()

    # DB has the pending lead with email saved correctly
    from sqlalchemy import select

    rows = (await session.execute(select(Lead))).scalars().all()
    assert len(rows) == 1
    assert rows[0].email == "marcus.tate@rpmliving.com"
    assert rows[0].status == "pending"
    assert rows[0].company == "RPM Living"


@pytest.mark.asyncio
async def test_webhook_inbound_rejects_invalid_email(client):
    bad = {
        "contact_name": "x",
        "contact_email": "not-an-email",
        "company": "X",
        "property_address": "1",
        "city": "A",
        "state": "B",
        "country": "US",
    }
    r = await client.post("/api/v1/webhooks/inbound", json=bad)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_webhook_inbound_rejects_missing_required_field(client):
    bad = {
        "contact_email": "ok@example.com",
        "company": "X",
        "city": "A",
        "state": "B",
        # missing contact_name and property_address
    }
    r = await client.post("/api/v1/webhooks/inbound", json=bad)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_webhook_optional_source_and_external_id_accepted(
    client, session
):
    """Without source/external_id should still 202."""
    minimal = {
        "contact_name": "Ada Lovelace",
        "contact_email": "ada@example.com",
        "company": "Babbage Inc",
        "property_address": "1 Engine St",
        "city": "London",
        "state": "ENG",
        "country": "UK",
    }
    r = await client.post("/api/v1/webhooks/inbound", json=minimal)
    assert r.status_code == 202
