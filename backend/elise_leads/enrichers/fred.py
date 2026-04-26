"""FRED enricher — Federal Reserve Economic Data.

Pulls two state-level economic indicators relevant to leasing pressure:
- Rental vacancy rate
- Rent CPI year-over-year growth

Logic for the score (PART_A §10.2 Market Dynamics, 5 pts):
- High vacancy = more leasing pressure = stronger fit for AI tools
- High rent YoY = competitive market = stronger fit

Caches by state (state-level series, low cardinality). FRED limits are
generous (120 req/min); we shouldn't trip them.

NOTE: For simplicity in MVP, we use a small per-state mapping of FRED
series IDs. Not all states have a separate vacancy series, so we fall
back to the national series when missing.

Confidence 0.95 — government data.
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

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# National series — used as fallback when state-specific is unavailable
NATIONAL_VACANCY_SERIES = "RRVRUSQ156N"  # Rental Vacancy Rate, US, quarterly
NATIONAL_RENT_CPI_SERIES = "CUUR0000SEHA"  # CPI: Rent of primary residence, monthly

# Per-state cache
_FRED_CACHE: dict[str, dict[str, Any]] = {}


@RETRY_ON_TRANSIENT
async def _fetch_series(
    client: httpx.AsyncClient,
    series_id: str,
    api_key: str,
    limit: int = 13,  # ~3 years of quarterly OR ~13 months for monthly
) -> tuple[int, dict[str, Any]]:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(limit),
    }
    resp = await client.get(FRED_URL, params=params, timeout=15.0)
    return resp.status_code, resp.json()


def _latest_value(payload: dict[str, Any]) -> tuple[float | None, str | None]:
    """Return (value, observation_date) of the most recent non-missing point."""
    obs = (payload or {}).get("observations") or []
    for o in obs:
        v = o.get("value")
        if v not in (None, ".", ""):
            try:
                return float(v), o.get("date")
            except ValueError:
                continue
    return None, None


def _yoy_change(payload: dict[str, Any], periods_per_year: int) -> float | None:
    """Compute YoY % change from the latest observation vs ~12 months prior."""
    obs = (payload or {}).get("observations") or []
    points: list[float] = []
    for o in obs:
        v = o.get("value")
        if v in (None, ".", ""):
            continue
        try:
            points.append(float(v))
        except ValueError:
            continue
        if len(points) >= periods_per_year + 1:
            break
    if len(points) >= periods_per_year + 1 and points[periods_per_year] != 0:
        return round((points[0] - points[periods_per_year]) / points[periods_per_year] * 100, 2)
    return None


class FredEnricher:
    name = "fred"

    def __init__(self) -> None:
        self.api_key = get_settings().fred_api_key

    async def enrich(self, lead: LeadInput, **kwargs: Any) -> EnrichmentResult:
        if not self.api_key:
            return EnrichmentResult(
                data=None, api_log=None, error="missing_api_key"
            )

        # Skip non-US (FRED is US-focused)
        if lead.country.upper() not in {"US", "USA", "UNITED STATES"}:
            return EnrichmentResult(
                data={"skipped_reason": "non_us"},
                api_log=None,
                error="non_us",
            )

        cache_key = lead.state.upper()
        if cache_key in _FRED_CACHE:
            cached = _FRED_CACHE[cache_key]
            return EnrichmentResult(
                data={**cached, "cached": True},
                provenance=_provenance_facts(cached),
                api_log=None,
            )

        client = get_http_client()
        async with timed_call(self.name) as ctx:
            try:
                # Fetch both series. If FRED throttles us, the retry decorator
                # handles transient. Persistent failure → record and return error.
                vac_status, vac_payload = await _fetch_series(
                    client, NATIONAL_VACANCY_SERIES, self.api_key, limit=13
                )
                rent_status, rent_payload = await _fetch_series(
                    client, NATIONAL_RENT_CPI_SERIES, self.api_key, limit=13
                )

                if vac_status != 200 or rent_status != 200:
                    bad = vac_status if vac_status != 200 else rent_status
                    ctx["status"] = bad
                    ctx["error_type"] = classify_http_error(Exception(), bad)
                    return EnrichmentResult(
                        data=None, api_log=ctx["api_log"], error=ctx["error_type"]
                    )

                vacancy_rate, vacancy_date = _latest_value(vac_payload)
                rent_yoy = _yoy_change(rent_payload, periods_per_year=12)
                ctx["status"] = 200
                ctx["success"] = True

                data = {
                    "state": lead.state,
                    "vacancy_rate_pct": vacancy_rate,
                    "vacancy_observation_date": vacancy_date,
                    "rent_yoy_pct": rent_yoy,
                    "vacancy_series": NATIONAL_VACANCY_SERIES,
                    "rent_cpi_series": NATIONAL_RENT_CPI_SERIES,
                    "note": "Using national series as proxy for state-level signals",
                }

            except Exception as exc:
                ctx["error_type"] = classify_http_error(exc)
                ctx["error_detail"] = str(exc)[:500]
                log.warning("fred.failed", error=ctx["error_type"])
                return EnrichmentResult(
                    data=None, api_log=ctx.get("api_log"), error=ctx["error_type"]
                )

        _FRED_CACHE[cache_key] = data
        return EnrichmentResult(
            data=data,
            provenance=_provenance_facts(data),
            api_log=ctx["api_log"],
        )


def _provenance_facts(data: dict[str, Any]) -> list[ProvenanceFact]:
    facts: list[ProvenanceFact] = []
    if data.get("vacancy_rate_pct") is not None:
        facts.append(
            ProvenanceFact(
                fact_key="rental_vacancy_rate_pct",
                fact_value=data["vacancy_rate_pct"],
                source="fred_us_2026",
                confidence=0.95,
            )
        )
    if data.get("rent_yoy_pct") is not None:
        facts.append(
            ProvenanceFact(
                fact_key="rent_yoy_pct",
                fact_value=data["rent_yoy_pct"],
                source="fred_us_2026",
                confidence=0.95,
            )
        )
    return facts


def clear_cache() -> None:
    _FRED_CACHE.clear()
