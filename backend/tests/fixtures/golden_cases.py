"""Golden cases — synthetic but realistic enrichment payloads keyed to a
specific lead profile, with the **expected tier** the rubric should produce.

These act as sanity checks for the scoring rubric:
- "Obvious Hot" / "Obvious Cold" must come out right
- "company > geography" verification (rural good operator → still Hot)
- Disqualifier verification (senior, commercial, non-US/CA)
- Missing-data graceful fallback

PART_A v2 §10.5 calls these out explicitly. Tests in test_rubric.py
iterate over `GOLDEN_CASES` and assert tier matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elise_leads.enrichers.base import LeadInput


@dataclass
class GoldenCase:
    name: str
    lead: LeadInput
    enriched: dict[str, Any]
    expected_tier: str
    expected_total_min: int | None = None
    expected_total_max: int | None = None
    expected_disqualified: bool = False
    description: str = ""


# ----------------------------------------------------------------------------
# Reusable enrichment payload helpers
# ----------------------------------------------------------------------------
_HOT_NMHC_GREYSTAR = {
    "matched": True,
    "rank": 1,
    "units_managed": 822_897,
    "official_name": "Greystar Real Estate Partners",
}
_HOT_WIKI = {
    "company_page": {
        "title": "Greystar",
        "summary": "Greystar is the largest US apartment manager.",
    },
    "company_scale_extracted": {"value": 800_000, "unit": "units"},
}
_HOT_NEWS = {
    "articles": [
        {
            "title": "Greystar acquires Alliance Residential",
            "source": "Wall Street Journal",
        }
    ],
    "signal_keywords": {"high": ["Greystar acquires Alliance"]},
    "premium_count": 1,
}
_HOT_CENSUS = {
    "geocoder": {"state_fips": "48", "county_fips": "453"},
    "acs": {
        "renter_pct": 0.68,
        "median_household_income": 78_000,
        "median_monthly_rent": 1700,
        "total_population": 4500,
    },
}
_HOT_WALK = {"walk_score": 92, "walk_description": "Walker's Paradise"}
_HOT_FRED = {"vacancy_rate_pct": 6.5, "rent_yoy_pct": 4.5}


def _make_lead(
    company: str = "Greystar",
    email: str = "sarah.johnson@greystar.com",
    state: str = "TX",
    country: str = "US",
) -> LeadInput:
    return LeadInput(
        name="Sarah Johnson",
        email=email,
        company=company,
        property_address="123 Main St",
        city="Austin",
        state=state,
        country=country,
    )


# ----------------------------------------------------------------------------
# The 9 cases
# ----------------------------------------------------------------------------
GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        name="Greystar Austin (perfect Hot)",
        lead=_make_lead(),
        enriched={
            "nmhc": _HOT_NMHC_GREYSTAR,
            "wiki": _HOT_WIKI,
            "news": _HOT_NEWS,
            "census": _HOT_CENSUS,
            "walkscore": _HOT_WALK,
            "fred": _HOT_FRED,
        },
        expected_tier="Hot",
        expected_total_min=85,
        description="Top NMHC + M&A news + great market + strong contact",
    ),
    GoldenCase(
        name="Asset Living secondary market (company > geography)",
        lead=_make_lead(
            company="Asset Living",
            email="mike.lee@assetliving.com",  # personal-format email
        ),
        enriched={
            # NMHC #2, large operator
            "nmhc": {"matched": True, "rank": 2, "units_managed": 257_123},
            "wiki": {
                "company_page": {
                    "title": "Asset Living",
                    "summary": "Asset Living is a large multifamily property manager.",
                }
            },
            "news": {
                "articles": [
                    {"title": "Asset Living launches new community", "source": "Multifamily Dive"},
                    {"title": "Asset Living Q2 update"},
                    {"title": "Industry roundup"},
                ],
                "signal_keywords": {"medium_high": ["Asset Living launches new community"]},
                "premium_count": 1,
            },
            # Secondary market (mid-tier southern city, not coastal premium)
            "census": {
                "geocoder": {"state_fips": "48"},
                "acs": {
                    "renter_pct": 0.45,  # modest renter density
                    "median_household_income": 56_000,
                    "median_monthly_rent": 1100,
                },
            },
            "walkscore": {"walk_score": 50, "walk_description": "Somewhat Walkable"},
            "fred": {"vacancy_rate_pct": 6.0, "rent_yoy_pct": 3.0},
        },
        expected_tier="Hot",
        expected_total_min=70,
        description=(
            "Verifies company-side dominance: NMHC #2 + expansion news + "
            "mid-tier geography → Hot. Demonstrates company-side carries."
        ),
    ),
    GoldenCase(
        name="Unknown @ Manhattan (geography ≠ score)",
        lead=_make_lead(
            company="Tiny Local Holdings",
            email="info@gmail.com",
            state="NY",
        ),
        enriched={
            "nmhc": {"matched": False},
            "wiki": {"company_page": None},
            "news": None,  # no news at all
            "census": {
                "acs": {
                    "renter_pct": 0.78,
                    "median_household_income": 95_000,
                    "median_monthly_rent": 2400,
                }
            },
            "walkscore": {"walk_score": 100, "walk_description": "Walker's Paradise"},
            "fred": {"vacancy_rate_pct": 3.0, "rent_yoy_pct": 6.0},
        },
        expected_tier="Cold",
        expected_total_max=58,
        description=(
            "Verifies great geography alone cannot redeem unknown small"
            " operator with weak contact (gmail + generic prefix)."
        ),
    ),
    GoldenCase(
        name="Senior living disqualifier",
        lead=_make_lead(
            company="Sunrise Senior Living LLC",
            email="alice@sunriseseniorliving.com",
        ),
        enriched={
            "nmhc": {"matched": False},
            "wiki": None,
            "news": None,
            "census": _HOT_CENSUS,
            "walkscore": _HOT_WALK,
            "fred": _HOT_FRED,
        },
        expected_tier="Cold",
        expected_disqualified=True,
        description=(
            "Even a great market profile can't override the vertical disqualifier."
        ),
    ),
    GoldenCase(
        name="Commercial real estate disqualifier",
        lead=_make_lead(
            company="Boston Properties (commercial real estate)",
            email="ops@bxp.com",
        ),
        enriched={"nmhc": {"matched": False}},
        expected_tier="Cold",
        expected_disqualified=True,
    ),
    GoldenCase(
        name="Toronto large operator (CA in scope)",
        lead=_make_lead(
            company="Greystar",
            email="sarah.johnson@greystar.com",
            state="ON",
            country="CA",
        ),
        enriched={
            "nmhc": _HOT_NMHC_GREYSTAR,
            "wiki": _HOT_WIKI,
            "news": _HOT_NEWS,
            # Census/WalkScore/FRED unavailable for Canada — median fallback
            "census": None,
            "walkscore": None,
            "fred": None,
        },
        expected_tier="Hot",
        expected_total_min=75,
        description=(
            "Canada is in service area. Geographic median fallbacks combined"
            " with strong company signals should still hit Hot."
        ),
    ),
    GoldenCase(
        name="Berlin operator (out of service area)",
        lead=_make_lead(
            company="Vonovia",
            email="info@vonovia.de",
            state="BE",
            country="DE",
        ),
        enriched={
            "nmhc": {"matched": False},
            "wiki": {
                "company_page": {
                    "title": "Vonovia",
                    "summary": "Vonovia is a residential real estate company.",
                }
            },
            "news": _HOT_NEWS,
        },
        expected_tier="Cold",
        expected_disqualified=True,
        description="Non-US/CA forces tier=Cold regardless of total points.",
    ),
    GoldenCase(
        name="Gmail.com lead at unknown operator (Cold by design)",
        lead=_make_lead(
            company="Some Apartment LLC",
            email="bob@gmail.com",
        ),
        enriched={
            "nmhc": {"matched": False},
            "wiki": None,
            "news": None,
            "census": _HOT_CENSUS,
            "walkscore": _HOT_WALK,
            "fred": _HOT_FRED,
        },
        expected_tier="Cold",
        expected_total_max=55,
        description=(
            "Verifies that great geography alone (max 30 pts) cannot offset "
            "weak company-side (15 pts) + free-email contact (3 pts). "
            "Reaches mid-40s — Cold by tier threshold but a high-Cold still "
            "worth a glance."
        ),
    ),
    GoldenCase(
        name="Missing Census data → median fallback",
        lead=_make_lead(),
        enriched={
            "nmhc": _HOT_NMHC_GREYSTAR,
            "wiki": _HOT_WIKI,
            "news": _HOT_NEWS,
            # Census + WalkScore + FRED all missing
            "census": None,
            "walkscore": None,
            "fred": None,
        },
        expected_tier="Hot",
        description=(
            "Pipeline degrades gracefully — median fallback keeps a great"
            " operator in Hot tier even when all geo APIs failed."
        ),
    ),
]
