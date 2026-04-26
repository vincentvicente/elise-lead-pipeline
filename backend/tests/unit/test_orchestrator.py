"""End-to-end test of the enrichment orchestrator.

Verifies:
- All 7 enrichers run for one lead
- Geocoder output flows correctly to Census ACS + WalkScore
- All results persist to DB (EnrichedData + Provenance + ApiLog rows)
- Per-source errors are recorded in EnrichedData.errors
"""

from __future__ import annotations

import os

# Ensure API keys are set before any settings cache build
os.environ["CENSUS_API_KEY"] = "test"
os.environ["NEWS_API_KEY"] = "test"
os.environ["WALKSCORE_API_KEY"] = "test"
os.environ["FRED_API_KEY"] = "test"

import pytest
import respx
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.enrichers import census_acs, fred, news, walkscore
from elise_leads.enrichers._http import close_http_client
from elise_leads.enrichers.base import LeadInput
from elise_leads.enrichers.orchestrator import (
    EnrichmentOrchestrator,
    persist_enrichment,
)
from elise_leads.models import ApiLog, EnrichedData, Lead, Provenance
from elise_leads.settings import get_settings


@pytest.fixture(autouse=True)
def _reset_caches():
    get_settings.cache_clear()
    census_acs.clear_cache()
    news.clear_cache()
    walkscore.clear_cache()
    fred.clear_cache()
    yield
    import asyncio

    asyncio.run(close_http_client())


def _seed_all_mocks(mock: respx.MockRouter) -> None:
    """Seed plausible responses for every external API."""
    # Wikipedia (called twice — company + city)
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
                                "title": "Austin, TX",
                                "fullurl": "https://en.wikipedia.org/wiki/Austin",
                                "extract": "Austin is the capital of Texas.",
                            }
                        }
                    }
                },
            ),
        ]
    )

    # NewsAPI
    mock.get("https://newsapi.org/v2/everything").mock(
        return_value=Response(
            200,
            json={
                "totalResults": 1,
                "articles": [
                    {
                        "title": "Greystar acquires Alliance Residential",
                        "description": "Apartment manager grows portfolio.",
                        "url": "https://wsj.com/x",
                        "source": {"name": "Wall Street Journal"},
                        "publishedAt": "2026-04-22T10:00:00Z",
                    }
                ],
            },
        )
    )

    # Census Geocoder
    mock.get(
        "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
    ).mock(
        return_value=Response(
            200,
            json={
                "result": {
                    "addressMatches": [
                        {
                            "matchedAddress": "123 Main St, Austin, TX",
                            "coordinates": {"x": -97.7431, "y": 30.2672},
                            "geographies": {
                                "Census Tracts": [
                                    {
                                        "STATE": "48",
                                        "COUNTY": "453",
                                        "TRACT": "001100",
                                        "GEOID": "48453001100",
                                        "NAME": "Census Tract 11",
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
        )
    )

    # Census ACS
    mock.get("https://api.census.gov/data/2022/acs/acs5").mock(
        return_value=Response(
            200,
            json=[
                ["B01003_001E", "B19013_001E", "B25008_001E", "B25008_003E", "B25064_001E", "B01002_001E", "state", "county", "tract"],
                ["3500", "72000", "1200", "850", "1500", "32.5", "48", "453", "001100"],
            ],
        )
    )

    # WalkScore
    mock.get("https://api.walkscore.com/score").mock(
        return_value=Response(
            200,
            json={
                "status": 1,
                "walkscore": 92,
                "transit": {"score": 65},
                "bike": {"score": 75},
                "snapped_lat": 30.2672,
                "snapped_lon": -97.7431,
            },
        )
    )

    # FRED — called twice (vacancy + rent CPI)
    mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
        side_effect=[
            Response(
                200,
                json={"observations": [{"date": "2026-01-01", "value": "6.2"}]},
            ),
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


@pytest.mark.asyncio
async def test_orchestrator_runs_all_enrichers() -> None:
    """One lead → 7 enricher results, all succeed with seeded responses."""
    lead_input = LeadInput(
        name="Sarah Johnson",
        email="sarah@greystar.com",
        company="Greystar",
        property_address="123 Main St",
        city="Austin",
        state="TX",
        country="US",
    )

    with respx.mock(assert_all_called=False) as mock:
        _seed_all_mocks(mock)
        bundle = await EnrichmentOrchestrator().enrich(lead_input)

    # All 7 enrichers should have produced data
    assert bundle.nmhc.succeeded
    assert bundle.wikipedia.succeeded
    assert bundle.news.succeeded
    assert bundle.fred.succeeded
    assert bundle.geocoder.succeeded
    assert bundle.census_acs.succeeded
    assert bundle.walkscore.succeeded

    # Errors map should be empty
    assert bundle.errors_map == {}

    # Provenance should aggregate across all sources
    fact_keys = {p.fact_key for p in bundle.all_provenance}
    assert "company_nmhc_rank" in fact_keys
    assert "wikipedia_company_exists" in fact_keys
    assert "geocoded_tract_fips" in fact_keys
    assert "census_renter_pct" in fact_keys
    assert "walk_score" in fact_keys
    assert "rental_vacancy_rate_pct" in fact_keys
    # NewsAPI provenance includes per-headline + signals
    assert any("news_headline" in k for k in fact_keys)


@pytest.mark.asyncio
async def test_orchestrator_handles_geocoder_failure_cleanly(
    session: AsyncSession,
) -> None:
    """If geocoder fails, ACS + WalkScore should be skipped with missing_geocode."""
    lead_input = LeadInput(
        name="Test",
        email="t@example.com",
        company="Unknown Local",
        property_address="999 Nowhere",
        city="Phantomville",
        state="ZZ",
        country="US",
    )

    with respx.mock(assert_all_called=False) as mock:
        _seed_all_mocks(mock)
        # Override geocoder with no-match
        mock.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
        ).mock(return_value=Response(200, json={"result": {"addressMatches": []}}))

        bundle = await EnrichmentOrchestrator().enrich(lead_input)

    # Geocoder failed → ACS + WalkScore skipped
    assert bundle.geocoder.error == "no_address_match"
    assert bundle.census_acs.error == "missing_geocode"
    assert bundle.walkscore.error == "missing_geocode"
    # But independents should still succeed
    assert bundle.nmhc.api_log is not None
    assert bundle.wikipedia.succeeded
    assert bundle.news.succeeded
    assert bundle.fred.succeeded

    # The errors_map should record all 3 failures
    assert "census_geocoder" in bundle.errors_map
    assert "census_acs" in bundle.errors_map
    assert "walkscore" in bundle.errors_map


@pytest.mark.asyncio
async def test_persist_enrichment_writes_to_db(session: AsyncSession) -> None:
    """Full bundle persistence: 1 EnrichedData + N Provenance + M ApiLog rows."""
    # Create a Lead first
    lead = Lead(
        name="Sarah Johnson",
        email="sarah@greystar.com",
        company="Greystar",
        property_address="123 Main St",
        city="Austin",
        state="TX",
        country="US",
        status="processing",
    )
    session.add(lead)
    await session.flush()

    lead_input = LeadInput(
        name=lead.name,
        email=lead.email,
        company=lead.company,
        property_address=lead.property_address,
        city=lead.city,
        state=lead.state,
        country=lead.country,
    )

    with respx.mock(assert_all_called=False) as mock:
        _seed_all_mocks(mock)
        bundle = await EnrichmentOrchestrator().enrich(lead_input)

    await persist_enrichment(session, lead, bundle, run_id=None)
    await session.commit()

    # 1 EnrichedData row
    er = (await session.execute(select(EnrichedData))).scalars().all()
    assert len(er) == 1
    assert er[0].lead_id == lead.id
    assert er[0].errors == {}  # all enrichers succeeded
    assert er[0].nmhc_json is not None
    assert er[0].census_json is not None
    assert er[0].census_json.get("acs", {}).get("renter_pct") == 0.7083

    # Provenance rows >= 6 (one per fact key, varies by source)
    pr = (await session.execute(select(Provenance))).scalars().all()
    assert len(pr) >= 6

    # ApiLog rows: NMHC + Wiki + News + FRED + Geocoder + ACS + WalkScore = 7
    al = (await session.execute(select(ApiLog))).scalars().all()
    assert len(al) >= 7
    successes = [x for x in al if x.success]
    assert len(successes) == len(al)  # all should be successful in this test
