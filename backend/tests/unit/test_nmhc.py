"""Tests for the NMHC static-lookup enricher.

No HTTP mocking needed — this enricher is pure in-memory lookup.
"""

from __future__ import annotations

import pytest

from elise_leads.enrichers.base import LeadInput
from elise_leads.enrichers.nmhc import NmhcEnricher, normalize_company_name


def make_lead(company: str) -> LeadInput:
    return LeadInput(
        name="Test User",
        email="test@example.com",
        company=company,
        property_address="123 Main St",
        city="Austin",
        state="TX",
        country="US",
    )


def test_normalize_drops_suffixes() -> None:
    assert normalize_company_name("Greystar, LLC") == "greystar"
    assert normalize_company_name("Asset Living Inc.") == "asset_living"
    assert normalize_company_name("The Bozzuto Group") == "bozzuto"


def test_normalize_collapses_punctuation() -> None:
    assert normalize_company_name("AvalonBay   Communities!!!") == "avalonbay"


@pytest.mark.asyncio
async def test_nmhc_exact_match_top10() -> None:
    enricher = NmhcEnricher()
    lead = make_lead("Greystar")
    result = await enricher.enrich(lead)

    assert result.succeeded
    assert result.data["matched"] is True
    assert result.data["rank"] == 1
    assert result.data["units_managed"] > 800_000
    # 3 provenance facts: rank, units, official name
    assert len(result.provenance) == 3
    assert all(p.confidence >= 0.95 for p in result.provenance)


@pytest.mark.asyncio
async def test_nmhc_match_with_suffix() -> None:
    """Greystar Real Estate Partners → still matches greystar."""
    enricher = NmhcEnricher()
    lead = make_lead("Greystar Real Estate Partners, LLC")
    result = await enricher.enrich(lead)

    assert result.succeeded
    assert result.data["matched"] is True
    assert result.data["rank"] == 1


@pytest.mark.asyncio
async def test_nmhc_no_match_returns_empty_provenance() -> None:
    enricher = NmhcEnricher()
    lead = make_lead("Some Tiny Local Operator XYZ")
    result = await enricher.enrich(lead)

    # Not an error — just no match
    assert result.error is None
    assert result.data == {"matched": False}
    assert result.provenance == []


@pytest.mark.asyncio
async def test_nmhc_top11_50_marked_correctly() -> None:
    enricher = NmhcEnricher()
    lead = make_lead("Equity Residential")
    result = await enricher.enrich(lead)

    assert result.succeeded
    assert result.data["rank"] == 11
    # Mid-tier operator
    assert 50_000 < result.data["units_managed"] < 100_000


@pytest.mark.asyncio
async def test_nmhc_api_log_recorded() -> None:
    enricher = NmhcEnricher()
    result = await enricher.enrich(make_lead("Greystar"))
    assert result.api_log is not None
    assert result.api_log.api_name == "nmhc"
    assert result.api_log.success is True
    assert result.api_log.duration_ms >= 0
