"""WalkScore enricher.

Returns walk / transit / bike scores for a property location. Free tier
is 5000 calls/day. Caches by 4-decimal rounded coordinates so nearby
properties (~10m apart) share a result.

Confidence 0.85 — proprietary algorithm but stable methodology.
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

WALKSCORE_URL = "https://api.walkscore.com/score"

# Coord-key cache (rounded to 4 decimals ≈ 10m precision)
_WS_CACHE: dict[tuple[float, float], dict[str, Any]] = {}


def _walk_description(score: int | None) -> str | None:
    """WalkScore's official tier labels (no need to call the API for this)."""
    if score is None:
        return None
    if score >= 90:
        return "Walker's Paradise"
    if score >= 70:
        return "Very Walkable"
    if score >= 50:
        return "Somewhat Walkable"
    if score >= 25:
        return "Car-Dependent"
    return "Car-Dependent"


@RETRY_ON_TRANSIENT
async def _fetch_walkscore(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    address: str,
    api_key: str,
) -> tuple[int, dict[str, Any]]:
    params = {
        "format": "json",
        "address": address,
        "lat": str(lat),
        "lon": str(lon),
        "transit": "1",
        "bike": "1",
        "wsapikey": api_key,
    }
    resp = await client.get(WALKSCORE_URL, params=params, timeout=15.0)
    return resp.status_code, resp.json()


class WalkScoreEnricher:
    name = "walkscore"

    def __init__(self) -> None:
        self.api_key = get_settings().walkscore_api_key

    async def enrich(self, lead: LeadInput, **kwargs: Any) -> EnrichmentResult:
        if not self.api_key:
            return EnrichmentResult(
                data=None, api_log=None, error="missing_api_key"
            )

        # Required upstream input (from CensusGeocoderEnricher)
        geo: dict[str, Any] | None = kwargs.get("geocode")
        if not geo or geo.get("latitude") is None or geo.get("longitude") is None:
            return EnrichmentResult(
                data=None, api_log=None, error="missing_geocode"
            )

        lat = round(float(geo["latitude"]), 4)
        lon = round(float(geo["longitude"]), 4)
        cache_key = (lat, lon)

        if cache_key in _WS_CACHE:
            cached = _WS_CACHE[cache_key]
            return EnrichmentResult(
                data={**cached, "cached": True},
                provenance=_provenance_facts(cached),
                api_log=None,
            )

        client = get_http_client()
        async with timed_call(self.name) as ctx:
            try:
                status, payload = await _fetch_walkscore(
                    client,
                    lat,
                    lon,
                    geo.get("matched_address") or lead.full_address,
                    self.api_key,
                )
                ctx["status"] = status

                if status != 200:
                    ctx["error_type"] = classify_http_error(Exception(), status)
                    return EnrichmentResult(
                        data=None, api_log=ctx["api_log"], error=ctx["error_type"]
                    )

                # WalkScore status code is in payload, not HTTP. 1=success.
                ws_status = payload.get("status")
                if ws_status != 1:
                    ctx["success"] = False
                    ctx["error_type"] = f"walkscore_status_{ws_status}"
                    return EnrichmentResult(
                        data=None,
                        api_log=ctx["api_log"],
                        error=ctx["error_type"],
                    )

                walk_score = payload.get("walkscore")
                data = {
                    "walk_score": walk_score,
                    "walk_description": _walk_description(walk_score),
                    "transit_score": (payload.get("transit") or {}).get("score"),
                    "bike_score": (payload.get("bike") or {}).get("score"),
                    "snapped_lat": payload.get("snapped_lat"),
                    "snapped_lon": payload.get("snapped_lon"),
                }
                ctx["success"] = True

            except Exception as exc:
                ctx["error_type"] = classify_http_error(exc)
                ctx["error_detail"] = str(exc)[:500]
                log.warning("walkscore.failed", error=ctx["error_type"])
                return EnrichmentResult(
                    data=None, api_log=ctx.get("api_log"), error=ctx["error_type"]
                )

        _WS_CACHE[cache_key] = data
        return EnrichmentResult(
            data=data,
            provenance=_provenance_facts(data),
            api_log=ctx["api_log"],
        )


def _provenance_facts(data: dict[str, Any]) -> list[ProvenanceFact]:
    facts: list[ProvenanceFact] = []
    if data.get("walk_score") is not None:
        facts.append(
            ProvenanceFact(
                fact_key="walk_score",
                fact_value=data["walk_score"],
                source="walkscore_api",
                confidence=0.85,
            )
        )
    if data.get("transit_score") is not None:
        facts.append(
            ProvenanceFact(
                fact_key="transit_score",
                fact_value=data["transit_score"],
                source="walkscore_api",
                confidence=0.85,
            )
        )
    return facts


def clear_cache() -> None:
    _WS_CACHE.clear()
