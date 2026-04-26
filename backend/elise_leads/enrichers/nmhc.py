"""NMHC Top 50 enricher.

Static lookup against `elise_leads/data/nmhc_top_50.json`. No HTTP, no
rate limit. Highest-confidence company-scale signal because EliseAI
already counts 38 of NMHC Top 50 as customers.

Match strategy: normalize the input company name (lowercase, strip
punctuation, remove common suffixes like "inc"/"llc"/"properties") and
look up by key. Also tries fuzzy substring match for cases like
"Greystar Real Estate" → "greystar".
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from importlib import resources
from typing import Any

from elise_leads.enrichers.base import (
    ApiLogEntry,
    EnrichmentResult,
    LeadInput,
    ProvenanceFact,
)

# ----------------------------------------------------------------------------
# Load the static dataset once at import time
# ----------------------------------------------------------------------------
_NMHC_DATA: dict[str, dict[str, Any]] = {}


def _load_nmhc() -> dict[str, dict[str, Any]]:
    global _NMHC_DATA
    if _NMHC_DATA:
        return _NMHC_DATA
    raw = resources.files("elise_leads.data").joinpath("nmhc_top_50.json").read_text()
    payload = json.loads(raw)
    _NMHC_DATA = payload.get("operators", {})
    return _NMHC_DATA


# ----------------------------------------------------------------------------
# Name normalization
# ----------------------------------------------------------------------------
_SUFFIXES = (
    "inc",
    "llc",
    "ltd",
    "corp",
    "corporation",
    "company",
    "co",
    "group",
    "properties",
    "communities",
    "trust",
    "reit",
    "realty",
    "real estate",
    "the",
)

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_company_name(name: str) -> str:
    """Lowercase + strip punctuation + drop common suffixes + collapse spaces."""
    s = _PUNCT_RE.sub(" ", name.lower())
    s = _WS_RE.sub(" ", s).strip()
    tokens = [t for t in s.split() if t not in _SUFFIXES]
    return "_".join(tokens)


# ----------------------------------------------------------------------------
# Matcher
# ----------------------------------------------------------------------------
def match_nmhc(company_name: str) -> dict[str, Any] | None:
    """Return the matched NMHC entry or None."""
    nmhc = _load_nmhc()
    key = normalize_company_name(company_name)

    # Exact key match
    if key in nmhc:
        return {**nmhc[key], "matched_key": key}

    # Substring match: incoming key contains a known operator key
    for known_key in nmhc:
        if known_key in key or key in known_key:
            # Only accept substring matches if they're at least 4 chars
            # (avoid "co" matching "asset_living" etc)
            common = known_key if known_key in key else key
            if len(common) >= 4:
                return {**nmhc[known_key], "matched_key": known_key}

    return None


# ----------------------------------------------------------------------------
# Enricher
# ----------------------------------------------------------------------------
class NmhcEnricher:
    """Static-lookup enricher; never makes HTTP calls."""

    name = "nmhc"

    async def enrich(self, lead: LeadInput, **kwargs: Any) -> EnrichmentResult:
        started_at = datetime.now(timezone.utc)
        match = match_nmhc(lead.company)

        api_log = ApiLogEntry(
            api_name=self.name,
            started_at=started_at,
            duration_ms=1,  # in-memory lookup
            http_status=None,
            success=True,
        )

        if match is None:
            return EnrichmentResult(
                data={"matched": False},
                provenance=[],
                api_log=api_log,
            )

        provenance = [
            ProvenanceFact(
                fact_key="company_nmhc_rank",
                fact_value=match["rank"],
                source="nmhc_top_50_2024",
                confidence=0.95,
            ),
            ProvenanceFact(
                fact_key="company_units_managed",
                fact_value=match["units_managed"],
                source="nmhc_top_50_2024",
                confidence=0.95,
            ),
            ProvenanceFact(
                fact_key="company_official_name",
                fact_value=match["official_name"],
                source="nmhc_top_50_2024",
                confidence=0.95,
            ),
        ]

        return EnrichmentResult(
            data={"matched": True, **match},
            provenance=provenance,
            api_log=api_log,
        )
