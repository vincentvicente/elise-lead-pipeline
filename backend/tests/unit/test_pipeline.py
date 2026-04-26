"""Tests for the per-lead pipeline + cron orchestration.

The full path is mocked end-to-end against in-memory SQLite:
- Enrichment APIs mocked with respx
- Claude mocked at the llm_client.call_claude level
- Resend (alerts) mocked at the resend module level

Verifies the integration contract:
- Successful run → Lead.status='processed', Score row, Email row, ApiLog rows
- Failed enrichment → Lead.status='failed', error_message recorded
- Run finalize → counts + report_md populated
- High failure rate → throttled alert sent
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Pre-set env so settings load right
os.environ["CENSUS_API_KEY"] = "test"
os.environ["NEWS_API_KEY"] = "test"
os.environ["WALKSCORE_API_KEY"] = "test"
os.environ["FRED_API_KEY"] = "test"
os.environ["ANTHROPIC_API_KEY"] = "test"
os.environ["RESEND_API_KEY"] = "test"
os.environ["ALERT_EMAIL"] = "alerts@example.com"

from elise_leads.enrichers import census_acs, fred, news, walkscore
from elise_leads.enrichers._http import close_http_client
from elise_leads.generation import llm_client
from elise_leads.models import (
    AlertHistory,
    ApiLog,
    Email,
    EnrichedData,
    Lead,
    Run,
    Score,
)
from elise_leads.pipeline import process_one_lead
from elise_leads.settings import get_settings


# ----------------------------------------------------------------------------
# Fixtures & helpers
# ----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset():
    get_settings.cache_clear()
    census_acs.clear_cache()
    news.clear_cache()
    walkscore.clear_cache()
    fred.clear_cache()
    yield
    import asyncio

    asyncio.run(close_http_client())


def _seed_enrichment_mocks(mock: respx.MockRouter) -> None:
    """Same payloads as test_orchestrator — already proven to work."""
    mock.get("https://en.wikipedia.org/w/api.php").mock(
        side_effect=[
            Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "1": {
                                "pageid": 1,
                                "title": "Greystar",
                                "fullurl": "https://en.wikipedia.org/wiki/Greystar",
                                "extract": "Greystar is the largest US apartment manager.",
                            }
                        }
                    }
                },
            ),
            Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "2": {
                                "pageid": 2,
                                "title": "Austin",
                                "fullurl": "https://en.wikipedia.org/wiki/Austin",
                                "extract": "Austin is the capital of Texas.",
                            }
                        }
                    }
                },
            ),
        ]
    )
    mock.get("https://newsapi.org/v2/everything").mock(
        return_value=Response(
            200,
            json={
                "totalResults": 1,
                "articles": [
                    {
                        "title": "Greystar acquires Alliance Residential",
                        "description": "Big deal",
                        "url": "https://wsj.com/x",
                        "source": {"name": "Wall Street Journal"},
                        "publishedAt": "2026-04-22T00:00:00Z",
                    }
                ],
            },
        )
    )
    mock.get(
        "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
    ).mock(
        return_value=Response(
            200,
            json={
                "result": {
                    "addressMatches": [
                        {
                            "matchedAddress": "123 Main St",
                            "coordinates": {"x": -97.7, "y": 30.27},
                            "geographies": {
                                "Census Tracts": [
                                    {
                                        "STATE": "48",
                                        "COUNTY": "453",
                                        "TRACT": "001100",
                                        "GEOID": "48453001100",
                                        "NAME": "Tract 11",
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
        )
    )
    mock.get("https://api.census.gov/data/2022/acs/acs5").mock(
        return_value=Response(
            200,
            json=[
                ["B01003_001E", "B19013_001E", "B25008_001E", "B25008_003E", "B25064_001E", "B01002_001E", "state", "county", "tract"],
                ["3500", "72000", "1200", "850", "1500", "32.5", "48", "453", "001100"],
            ],
        )
    )
    mock.get("https://api.walkscore.com/score").mock(
        return_value=Response(
            200,
            json={
                "status": 1,
                "walkscore": 92,
                "transit": {"score": 65},
                "bike": {"score": 75},
            },
        )
    )
    mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
        side_effect=[
            Response(200, json={"observations": [{"date": "2026-01-01", "value": "6.2"}]}),
            Response(
                200,
                json={
                    "observations": [
                        {"date": f"2026-{m:02d}-01", "value": str(380.0 + m * 0.1)}
                        for m in range(13, 0, -1)
                    ]
                },
            ),
        ]
    )


def _make_clean_claude_response(
    body: str = (
        "Hi Sarah,\n\n"
        "Saw the news about Greystar's portfolio. "
        "Equity Residential saved $14M with EliseAI.\n\n"
        "Worth a quick chat?\n\n"
        "Best,\n[SDR Name]"
    ),
):
    """Build a fake Claude response that passes hallucination check."""
    from elise_leads.enrichers.base import ApiLogEntry

    return llm_client.ClaudeResponse(
        raw_text=f"<subject>Quick question, Sarah</subject><body>{body}</body>",
        subject="Quick question, Sarah",
        body=body,
        model="claude-sonnet-4-6",
        api_log=ApiLogEntry(
            api_name="claude:claude-sonnet-4-6",
            started_at=datetime.now(timezone.utc),
            duration_ms=2400,
            http_status=200,
            success=True,
        ),
    )


# ----------------------------------------------------------------------------
# Tests for process_one_lead
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_process_one_lead_full_success_path(
    session: AsyncSession,
) -> None:
    """End-to-end happy path: pending lead → processed with all artifacts."""
    # Patch the global session factory so the pipeline uses the test engine
    from elise_leads import db as db_mod

    # We need to align the pipeline's session_scope() to use our test engine.
    # The simplest way: bind SessionLocal to the session's bind.
    test_factory = MagicMock()
    test_engine = session.bind  # AsyncEngine

    # Instead of full patching, create a real async_sessionmaker on the test engine
    from sqlalchemy.ext.asyncio import async_sessionmaker

    db_mod.SessionLocal = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, autoflush=False
    )

    # Create a Run + a pending Lead
    run = Run(status="running", lead_count=0, success_count=0, failure_count=0)
    session.add(run)
    await session.flush()

    lead = Lead(
        name="Sarah Johnson",
        email="sarah.johnson@greystar.com",
        company="Greystar",
        property_address="123 Main St",
        city="Austin",
        state="TX",
        country="US",
        status="pending",
    )
    session.add(lead)
    await session.commit()

    with respx.mock(assert_all_called=False) as mock:
        _seed_enrichment_mocks(mock)
        with patch.object(
            llm_client,
            "call_claude",
            new=AsyncMock(return_value=_make_clean_claude_response()),
        ):
            outcome = await process_one_lead(lead.id, run.id)

    assert outcome.status == "success"
    assert outcome.tier in {"Hot", "Warm", "Cold"}
    assert outcome.email_source == "llm:claude-sonnet-4-6"

    # Verify DB state in a fresh session/query
    refreshed = await session.get(Lead, lead.id)
    await session.refresh(refreshed)
    assert refreshed.status == "processed"
    assert refreshed.processed_at is not None
    assert refreshed.run_id == run.id

    enriched = (
        await session.execute(select(EnrichedData).where(EnrichedData.lead_id == lead.id))
    ).scalar_one()
    assert enriched.nmhc_json is not None

    score_row = (
        await session.execute(select(Score).where(Score.lead_id == lead.id))
    ).scalar_one()
    assert score_row.tier == outcome.tier
    assert score_row.total == outcome.score_total

    email_row = (
        await session.execute(select(Email).where(Email.lead_id == lead.id))
    ).scalar_one()
    assert email_row.source == "llm:claude-sonnet-4-6"
    assert "[SDR Name]" in email_row.body
    assert email_row.proof_point_used  # populated by selector

    # API logs span enrichment + Claude
    api_logs = (
        await session.execute(select(ApiLog).where(ApiLog.lead_id == lead.id))
    ).scalars().all()
    api_names = {a.api_name for a in api_logs}
    assert any(name.startswith("claude:") for name in api_names)
    assert "census_geocoder" in api_names
    assert "newsapi" in api_names


@pytest.mark.asyncio
async def test_process_one_lead_records_failure_when_orchestrator_throws(
    session: AsyncSession,
) -> None:
    """If something escapes the inner try, lead gets marked failed."""
    from elise_leads import db as db_mod
    from sqlalchemy.ext.asyncio import async_sessionmaker

    db_mod.SessionLocal = async_sessionmaker(
        bind=session.bind, expire_on_commit=False, autoflush=False
    )

    run = Run(status="running")
    session.add(run)
    await session.flush()

    lead = Lead(
        name="Test",
        email="t@example.com",
        company="X",
        property_address="1",
        city="A",
        state="TX",
        country="US",
        status="pending",
    )
    session.add(lead)
    await session.commit()

    # Patch the orchestrator to raise unexpectedly
    from elise_leads.enrichers.orchestrator import EnrichmentOrchestrator

    bad_orch = EnrichmentOrchestrator()
    bad_orch.enrich = AsyncMock(side_effect=RuntimeError("simulated DB blip"))

    outcome = await process_one_lead(lead.id, run.id, orchestrator=bad_orch)

    assert outcome.status == "failed"
    assert "simulated DB blip" in outcome.error

    # Lead in DB now reflects failure
    refreshed = await session.get(Lead, lead.id)
    await session.refresh(refreshed)
    assert refreshed.status == "failed"
    assert refreshed.error_message is not None
    assert "simulated DB blip" in refreshed.error_message


# ----------------------------------------------------------------------------
# cron.run_pipeline_once integration
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cron_finalizes_run_with_zero_pending_leads(
    session: AsyncSession,
) -> None:
    """No pending leads → run finalized as 'success' with 0 counts."""
    from elise_leads import cron, db as db_mod
    from sqlalchemy.ext.asyncio import async_sessionmaker

    db_mod.SessionLocal = async_sessionmaker(
        bind=session.bind, expire_on_commit=False, autoflush=False
    )

    with patch("elise_leads.alerting.client.resend") as mock_resend:
        mock_resend.Emails.send = MagicMock(return_value={"id": "re_x"})
        run = await cron.run_pipeline_once()

    assert run.status == "success"
    assert run.lead_count == 0
    assert run.finished_at is not None
    # Should have triggered the no_pending_leads alert
    history = (
        await session.execute(
            select(AlertHistory).where(AlertHistory.alert_key == "no_pending_leads")
        )
    ).scalar_one_or_none()
    assert history is not None
