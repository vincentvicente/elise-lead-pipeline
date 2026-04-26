"""Tests for HTTP-based enrichers (Wikipedia / Census / News / WalkScore / FRED).

Uses respx to mock httpx calls. Each test seeds a realistic API response,
then verifies the enricher correctly parses → produces data + provenance.

Tests reset module-level caches between runs to avoid cross-test pollution.
"""

from __future__ import annotations

import os

# Ensure settings have API keys before settings cache is populated
os.environ["CENSUS_API_KEY"] = "test-census-key"
os.environ["NEWS_API_KEY"] = "test-news-key"
os.environ["WALKSCORE_API_KEY"] = "test-walkscore-key"
os.environ["FRED_API_KEY"] = "test-fred-key"

import pytest
import respx
from httpx import Response

from elise_leads.enrichers import census_acs, fred, news, walkscore
from elise_leads.enrichers._http import close_http_client
from elise_leads.enrichers.base import LeadInput
from elise_leads.enrichers.census_acs import CensusAcsEnricher
from elise_leads.enrichers.census_geocoder import CensusGeocoderEnricher
from elise_leads.enrichers.fred import FredEnricher
from elise_leads.enrichers.news import NewsApiEnricher
from elise_leads.enrichers.walkscore import WalkScoreEnricher
from elise_leads.enrichers.wikipedia import WikipediaEnricher
from elise_leads.settings import get_settings


@pytest.fixture(autouse=True)
def _reset_caches_and_settings():
    """Clear all module-level caches and rebuild settings before each test."""
    get_settings.cache_clear()
    census_acs.clear_cache()
    news.clear_cache()
    walkscore.clear_cache()
    fred.clear_cache()
    yield
    # Force-close httpx client so respx can re-mount cleanly
    import asyncio

    asyncio.run(close_http_client())


def lead(**overrides) -> LeadInput:
    base = dict(
        name="Sarah Johnson",
        email="sarah@greystar.com",
        company="Greystar",
        property_address="123 Main St",
        city="Austin",
        state="TX",
        country="US",
    )
    base.update(overrides)
    return LeadInput(**base)


# ----------------------------------------------------------------------------
# Wikipedia
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_wikipedia_extracts_company_summary() -> None:
    company_payload = {
        "query": {
            "pages": {
                "12345": {
                    "pageid": 12345,
                    "title": "Greystar Real Estate Partners",
                    "fullurl": "https://en.wikipedia.org/wiki/Greystar",
                    "extract": (
                        "Greystar Real Estate Partners is the largest "
                        "apartment manager in the US, managing over 800,000 units."
                    ),
                }
            }
        }
    }
    city_payload = {
        "query": {
            "pages": {
                "67890": {
                    "pageid": 67890,
                    "title": "Austin, TX",
                    "fullurl": "https://en.wikipedia.org/wiki/Austin,_Texas",
                    "extract": "Austin is the capital of Texas.",
                }
            }
        }
    }

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://en.wikipedia.org/w/api.php").mock(
            side_effect=[
                Response(200, json=company_payload),
                Response(200, json=city_payload),
            ]
        )
        result = await WikipediaEnricher().enrich(lead())

    assert result.succeeded
    assert "Greystar" in result.data["company_page"]["title"]
    assert result.data["company_scale_extracted"]["value"] == 800_000
    assert result.data["company_scale_extracted"]["unit"] == "units"
    assert result.data["company_largest_claim"] == "largest"
    # Should produce existence + scale + largest + city = 4 facts
    assert len(result.provenance) == 4


@pytest.mark.asyncio
async def test_wikipedia_handles_missing_page() -> None:
    missing = {"query": {"pages": {"-1": {"missing": ""}}}}
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://en.wikipedia.org/w/api.php").mock(
            return_value=Response(200, json=missing)
        )
        result = await WikipediaEnricher().enrich(lead(company="Some Tiny Co"))

    # No page = no error, just empty data
    assert result.error is None
    assert result.data["company_page"] is None
    assert result.provenance == []


# ----------------------------------------------------------------------------
# Census Geocoder
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_census_geocoder_returns_tract_coords() -> None:
    payload = {
        "result": {
            "addressMatches": [
                {
                    "matchedAddress": "123 Main St, Austin, TX, 78701",
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
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
        ).mock(return_value=Response(200, json=payload))

        result = await CensusGeocoderEnricher().enrich(lead())

    assert result.succeeded
    assert result.data["state_fips"] == "48"
    assert result.data["county_fips"] == "453"
    assert result.data["tract_fips"] == "001100"
    assert result.data["latitude"] == 30.2672
    assert result.data["longitude"] == -97.7431
    assert len(result.provenance) == 1


@pytest.mark.asyncio
async def test_census_geocoder_skips_non_us() -> None:
    """Non-US addresses skip cleanly; downstream enrichers will skip too."""
    result = await CensusGeocoderEnricher().enrich(lead(country="DE"))
    assert result.error == "non_us_address"
    assert result.api_log is None  # never made an HTTP call


@pytest.mark.asyncio
async def test_census_geocoder_no_match() -> None:
    """Garbage address returns empty matches → recorded as no_address_match."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
        ).mock(return_value=Response(200, json={"result": {"addressMatches": []}}))

        result = await CensusGeocoderEnricher().enrich(lead())

    assert result.error == "no_address_match"
    assert result.api_log is not None  # the call did happen


# ----------------------------------------------------------------------------
# Census ACS (depends on geocoder output)
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_census_acs_parses_demographics() -> None:
    # ACS returns [[headers], [values]] format
    payload = [
        [
            "B01003_001E",
            "B19013_001E",
            "B25008_001E",
            "B25008_003E",
            "B25064_001E",
            "B01002_001E",
            "state",
            "county",
            "tract",
        ],
        ["3500", "72000", "1200", "850", "1500", "32.5", "48", "453", "001100"],
    ]
    geo = {
        "state_fips": "48",
        "county_fips": "453",
        "tract_fips": "001100",
        "latitude": 30.2,
        "longitude": -97.7,
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.census.gov/data/2022/acs/acs5").mock(
            return_value=Response(200, json=payload)
        )
        result = await CensusAcsEnricher().enrich(lead(), geocode=geo)

    assert result.succeeded
    assert result.data["total_population"] == 3500
    assert result.data["median_household_income"] == 72_000
    # renter_pct derived: 850 / 1200 = 0.7083
    assert result.data["renter_pct"] == 0.7083
    assert len(result.provenance) >= 4


@pytest.mark.asyncio
async def test_census_acs_handles_na_sentinel() -> None:
    """Census uses -666666666 for missing values; enricher coerces to None."""
    payload = [
        ["B01003_001E", "B19013_001E", "B25008_001E", "B25008_003E", "B25064_001E", "B01002_001E", "state", "county", "tract"],
        ["3500", "-666666666", "1200", "850", "-666666666", "32.5", "48", "453", "001100"],
    ]
    geo = {"state_fips": "48", "county_fips": "453", "tract_fips": "001100"}

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.census.gov/data/2022/acs/acs5").mock(
            return_value=Response(200, json=payload)
        )
        result = await CensusAcsEnricher().enrich(lead(), geocode=geo)

    assert result.succeeded
    assert result.data["median_household_income"] is None
    assert result.data["median_monthly_rent"] is None
    assert result.data["total_population"] == 3500


@pytest.mark.asyncio
async def test_census_acs_skips_without_geocode() -> None:
    """Without geocoder output, ACS can't run."""
    result = await CensusAcsEnricher().enrich(lead(), geocode=None)
    assert result.error == "missing_geocode"
    assert result.api_log is None


# ----------------------------------------------------------------------------
# NewsAPI
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_newsapi_extracts_signal_keywords() -> None:
    payload = {
        "totalResults": 2,
        "articles": [
            {
                "title": "Greystar acquires Alliance Residential",
                "description": "Largest US apartment manager expands portfolio.",
                "url": "https://wsj.com/x",
                "source": {"name": "Wall Street Journal"},
                "publishedAt": "2026-04-22T10:00:00Z",
            },
            {
                "title": "New apartment community opens in Austin",
                "description": "Greystar launches multifamily property.",
                "url": "https://realdeal.com/y",
                "source": {"name": "Real Deal"},
                "publishedAt": "2026-04-15T10:00:00Z",
            },
        ],
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://newsapi.org/v2/everything").mock(
            return_value=Response(200, json=payload)
        )
        result = await NewsApiEnricher().enrich(lead())

    assert result.succeeded
    assert "high" in result.data["signal_keywords"]  # "acquires" → high
    assert "medium_high" in result.data["signal_keywords"]  # "launched"
    assert result.data["premium_count"] == 2  # WSJ + Real Deal both premium
    # Premium-source articles → 0.85 confidence
    assert any(p.confidence >= 0.85 for p in result.provenance)


@pytest.mark.asyncio
async def test_newsapi_caches_by_company_name() -> None:
    """Second call with same company should hit cache, not HTTP."""
    payload = {
        "totalResults": 1,
        "articles": [
            {
                "title": "Greystar news",
                "description": "Some apartment news",
                "url": "https://example.com",
                "source": {"name": "Example News"},
                "publishedAt": "2026-04-20T10:00:00Z",
            }
        ],
    }
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://newsapi.org/v2/everything").mock(
            return_value=Response(200, json=payload)
        )
        await NewsApiEnricher().enrich(lead())
        await NewsApiEnricher().enrich(lead())  # cached

        assert route.call_count == 1


@pytest.mark.asyncio
async def test_newsapi_handles_quota_exceeded() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://newsapi.org/v2/everything").mock(
            return_value=Response(426, json={"status": "error"})
        )
        result = await NewsApiEnricher().enrich(lead())

    assert result.error == "quota_exceeded"
    assert result.data is None


# ----------------------------------------------------------------------------
# WalkScore
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_walkscore_returns_walk_transit_bike() -> None:
    payload = {
        "status": 1,
        "walkscore": 92,
        "transit": {"score": 65},
        "bike": {"score": 75},
        "snapped_lat": 30.2672,
        "snapped_lon": -97.7431,
    }
    geo = {
        "matched_address": "123 Main St, Austin, TX",
        "latitude": 30.2672,
        "longitude": -97.7431,
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.walkscore.com/score").mock(
            return_value=Response(200, json=payload)
        )
        result = await WalkScoreEnricher().enrich(lead(), geocode=geo)

    assert result.succeeded
    assert result.data["walk_score"] == 92
    assert result.data["walk_description"] == "Walker's Paradise"
    assert result.data["transit_score"] == 65
    assert len(result.provenance) == 2


@pytest.mark.asyncio
async def test_walkscore_handles_walkscore_status_error() -> None:
    """WalkScore status field non-1 means logical error, even with HTTP 200."""
    payload = {"status": 41}
    geo = {"latitude": 30.0, "longitude": -97.0}
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.walkscore.com/score").mock(
            return_value=Response(200, json=payload)
        )
        result = await WalkScoreEnricher().enrich(lead(), geocode=geo)

    assert result.error == "walkscore_status_41"


# ----------------------------------------------------------------------------
# FRED
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fred_extracts_vacancy_and_yoy() -> None:
    vacancy_payload = {
        "observations": [
            {"date": "2026-01-01", "value": "6.2"},
            {"date": "2025-10-01", "value": "6.0"},
        ]
    }
    rent_payload = {
        "observations": [
            {"date": f"2026-{m:02d}-01", "value": str(380.0 + m * 0.1)} for m in range(13, 0, -1)
        ]
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
            side_effect=[
                Response(200, json=vacancy_payload),
                Response(200, json=rent_payload),
            ]
        )
        result = await FredEnricher().enrich(lead())

    assert result.succeeded
    assert result.data["vacancy_rate_pct"] == 6.2
    assert result.data["rent_yoy_pct"] is not None
