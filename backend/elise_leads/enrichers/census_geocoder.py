"""Census Geocoder — converts a US street address to FIPS codes + coords.

This is a free, no-key endpoint provided by the U.S. Census Bureau:
    https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress

Output is consumed downstream by:
- CensusAcsEnricher (needs state/county/tract for ACS variable lookups)
- WalkScoreEnricher (needs lat/lon)

So this enricher MUST run before those two. The orchestrator handles
ordering; failures here propagate as an error and skip both downstream
enrichers (they fall back to median scores).
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

GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
)


@RETRY_ON_TRANSIENT
async def _fetch_geo(
    client: httpx.AsyncClient, address: str
) -> tuple[int, dict[str, Any]]:
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }
    resp = await client.get(GEOCODER_URL, params=params, timeout=20.0)
    return resp.status_code, resp.json()


def _parse_first_match(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract tract/coords from the first address match.

    Census responses are deeply nested:
        result.addressMatches[0].coordinates.{x,y}
        result.addressMatches[0].geographies."Census Tracts"[0].{STATE, COUNTY, TRACT}
    """
    matches = (payload or {}).get("result", {}).get("addressMatches") or []
    if not matches:
        return None
    m = matches[0]
    coords = m.get("coordinates") or {}
    geos = (m.get("geographies") or {}).get("Census Tracts") or []
    if not geos:
        return None
    g = geos[0]
    return {
        "matched_address": m.get("matchedAddress"),
        "longitude": coords.get("x"),
        "latitude": coords.get("y"),
        "state_fips": g.get("STATE"),
        "county_fips": g.get("COUNTY"),
        "tract_fips": g.get("TRACT"),
        "geoid": g.get("GEOID"),
        "tract_name": g.get("NAME"),
    }


class CensusGeocoderEnricher:
    name = "census_geocoder"

    async def enrich(self, lead: LeadInput, **kwargs: Any) -> EnrichmentResult:
        # US-only API; for non-US leads, skip cleanly (orchestrator will
        # also skip downstream Census ACS / WalkScore).
        if lead.country.upper() not in {"US", "USA", "UNITED STATES"}:
            return EnrichmentResult(
                data={"skipped_reason": "non_us_address", "country": lead.country},
                provenance=[],
                api_log=None,
                error="non_us_address",
            )

        client = get_http_client()
        async with timed_call(self.name) as ctx:
            try:
                status, payload = await _fetch_geo(client, lead.full_address)
                ctx["status"] = status

                if status != 200:
                    ctx["error_type"] = classify_http_error(Exception(), status)
                    return EnrichmentResult(
                        data=None, api_log=ctx["api_log"], error=ctx["error_type"]
                    )

                match = _parse_first_match(payload)
                ctx["success"] = match is not None
                if match is None:
                    ctx["error_type"] = "no_address_match"
                    return EnrichmentResult(
                        data={"no_match": True},
                        api_log=ctx["api_log"],
                        error="no_address_match",
                    )

            except Exception as exc:
                ctx["error_type"] = classify_http_error(exc)
                ctx["error_detail"] = str(exc)[:500]
                log.warning(
                    "geocoder.failed",
                    address=lead.full_address,
                    error=ctx["error_type"],
                )
                return EnrichmentResult(
                    data=None, api_log=ctx.get("api_log"), error=ctx["error_type"]
                )

        # Provenance — coords/tract are very high confidence (gov data)
        provenance = [
            ProvenanceFact(
                fact_key="geocoded_tract_fips",
                fact_value=match["geoid"],
                source="census_geocoder_2026",
                confidence=0.95,
            ),
        ]

        return EnrichmentResult(
            data=match,
            provenance=provenance,
            api_log=ctx["api_log"],
        )
