"""Census ACS 5-Year enricher.

Pulls tract-level demographics for the property location:
- B01003_001E — total population
- B19013_001E — median household income
- B25008_001E — total occupied housing
- B25008_003E — renter-occupied housing
- B25064_001E — median monthly rent
- B01002_001E — median age

Then computes derived `renter_pct = B25008_003E / B25008_001E`.

Caches by tract (state+county+tract) since same tract → same data.

Confidence 0.95 — government data is the gold standard for this category.
"""

from __future__ import annotations

from typing import Any

import httpx

from elise_leads.enrichers._http import (
    RETRY_ON_TRANSIENT,
    classify_http_error,
    get_http_client,
    log,
    timed_call,
)
from elise_leads.enrichers.base import (
    EnrichmentResult,
    LeadInput,
    ProvenanceFact,
)
from elise_leads.settings import get_settings

ACS_URL = "https://api.census.gov/data/2022/acs/acs5"

VARIABLES = {
    "B01003_001E": "total_population",
    "B19013_001E": "median_household_income",
    "B25008_001E": "total_occupied_housing",
    "B25008_003E": "renter_occupied_housing",
    "B25064_001E": "median_monthly_rent",
    "B01002_001E": "median_age",
}

# Census uses this sentinel for missing/suppressed values
NA_SENTINEL = -666666666

# Per-tract cache — same tract → same data, very high hit rate when leads
# share neighborhoods. Module-level dict; not persisted across processes.
_TRACT_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


@RETRY_ON_TRANSIENT
async def _fetch_acs(
    client: httpx.AsyncClient,
    state_fips: str,
    county_fips: str,
    tract_fips: str,
    api_key: str,
) -> tuple[int, list]:
    params = {
        "get": ",".join(VARIABLES.keys()),
        "for": f"tract:{tract_fips}",
        "in": f"state:{state_fips} county:{county_fips}",
    }
    if api_key:
        params["key"] = api_key

    resp = await client.get(ACS_URL, params=params, timeout=15.0)
    return resp.status_code, resp.json() if resp.headers.get("content-type", "").startswith("application/json") else []


def _row_to_dict(rows: list) -> dict[str, Any] | None:
    """ACS returns [[header...], [values...]]. Build a flat dict."""
    if not rows or len(rows) < 2:
        return None
    headers, values = rows[0], rows[1]
    out: dict[str, Any] = {}
    for h, v in zip(headers, values, strict=False):
        if h in VARIABLES:
            try:
                num = int(v)
                out[VARIABLES[h]] = None if num == NA_SENTINEL else num
            except (ValueError, TypeError):
                out[VARIABLES[h]] = None
    return out


def _add_derived(d: dict[str, Any]) -> dict[str, Any]:
    """Compute renter_pct from raw counts."""
    total = d.get("total_occupied_housing")
    renter = d.get("renter_occupied_housing")
    if total and renter is not None and total > 0:
        d["renter_pct"] = round(renter / total, 4)
    return d


class CensusAcsEnricher:
    name = "census_acs"

    def __init__(self) -> None:
        self.api_key = get_settings().census_api_key

    async def enrich(self, lead: LeadInput, **kwargs: Any) -> EnrichmentResult:
        # Required upstream input (from CensusGeocoderEnricher)
        geo: dict[str, Any] | None = kwargs.get("geocode")
        if not geo or not geo.get("tract_fips"):
            return EnrichmentResult(
                data=None,
                api_log=None,
                error="missing_geocode",
            )

        cache_key = (geo["state_fips"], geo["county_fips"], geo["tract_fips"])
        if cache_key in _TRACT_CACHE:
            cached = _TRACT_CACHE[cache_key]
            return EnrichmentResult(
                data={**cached, "cached": True},
                provenance=_provenance_facts(cached),
                api_log=None,  # cached lookup, not an external call
            )

        client = get_http_client()
        async with timed_call(self.name) as ctx:
            try:
                status, payload = await _fetch_acs(
                    client,
                    geo["state_fips"],
                    geo["county_fips"],
                    geo["tract_fips"],
                    self.api_key,
                )
                ctx["status"] = status
                if status != 200:
                    ctx["error_type"] = classify_http_error(Exception(), status)
                    return EnrichmentResult(
                        data=None, api_log=ctx["api_log"], error=ctx["error_type"]
                    )

                data = _row_to_dict(payload)
                ctx["success"] = data is not None
                if data is None:
                    ctx["error_type"] = "empty_response"
                    return EnrichmentResult(
                        data=None, api_log=ctx["api_log"], error="empty_response"
                    )
                _add_derived(data)

            except Exception as exc:
                ctx["error_type"] = classify_http_error(exc)
                ctx["error_detail"] = str(exc)[:500]
                log.warning("census_acs.failed", error=ctx["error_type"])
                return EnrichmentResult(
                    data=None, api_log=ctx.get("api_log"), error=ctx["error_type"]
                )

        # Cache and return
        _TRACT_CACHE[cache_key] = data
        return EnrichmentResult(
            data=data,
            provenance=_provenance_facts(data),
            api_log=ctx["api_log"],
        )


def _provenance_facts(data: dict[str, Any]) -> list[ProvenanceFact]:
    """Emit one ProvenanceFact per non-null Census variable."""
    facts: list[ProvenanceFact] = []
    for key in (
        "renter_pct",
        "median_household_income",
        "median_monthly_rent",
        "total_population",
        "median_age",
    ):
        if data.get(key) is not None:
            facts.append(
                ProvenanceFact(
                    fact_key=f"census_{key}",
                    fact_value=data[key],
                    source="census_acs_2022",
                    confidence=0.95,
                )
            )
    return facts


def clear_cache() -> None:
    """Test helper — clear the per-tract cache."""
    _TRACT_CACHE.clear()
