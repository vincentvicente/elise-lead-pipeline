"""Top-level scoring entry point.

Combines per-dimension scores into a `LeadScore` (0–100 + tier + breakdown +
reasons), applying the v2 rubric:

  Total = 100
    Company-side (55):  scale 25 + buy_intent 20 + vertical 10
    Geography (30):     market 15 + property 10 + dynamics 5
    Contact-side (15):  domain 5 + match 5 + prefix 5

  Tier:  ≥75 Hot · 55–74 Warm · <55 Cold

Hard disqualifiers (override tier to Cold):
  - Vertical Fit detects senior-living or commercial real-estate keywords
  - Lead.country is not US/CA (out of EliseAI service area)

Missing-data fallbacks already live inside each DimensionResult; the
rubric just sums and labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from elise_leads.enrichers.base import LeadInput
from elise_leads.scoring import dimensions

Tier = Literal["Hot", "Warm", "Cold"]


@dataclass
class LeadScore:
    total: int  # 0–100
    tier: Tier
    breakdown: dict[str, int]  # per-dimension points
    reasons: list[str]  # all dimension reasons concatenated
    disqualified: bool = False
    disqualifier_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def compute_tier(total: int) -> Tier:
    if total >= 75:
        return "Hot"
    if total >= 55:
        return "Warm"
    return "Cold"


def _is_in_service_area(country: str) -> bool:
    """EliseAI serves US + Canada (per public footprint research)."""
    c = (country or "").upper()
    return c in {"US", "USA", "UNITED STATES", "CA", "CAN", "CANADA"}


def score(
    lead: LeadInput,
    enriched: dict[str, Any],
) -> LeadScore:
    """Compute the v2 score for one lead.

    `enriched` is a dict keyed by source: nmhc / wikipedia / news /
    walkscore / fred / census (with sub-keys 'geocoder' and 'acs').
    Each value is the JSON payload from the enricher (or None).
    """
    nmhc = enriched.get("nmhc")
    wiki = enriched.get("wiki")
    news = enriched.get("news")
    walk = enriched.get("walkscore")
    fred = enriched.get("fred")
    census = enriched.get("census")

    wiki_summary: str | None = None
    if wiki and wiki.get("company_page"):
        wiki_summary = wiki["company_page"].get("summary")

    # ----------- Per-dimension scoring -----------
    co_scale = dimensions.score_company_scale(nmhc, wiki, news)
    buy_intent = dimensions.score_buy_intent(news)
    vertical = dimensions.score_vertical_fit(lead.company, wiki_summary)
    market = dimensions.score_market_fit(census)
    property_ = dimensions.score_property_fit(walk, census)
    dynamics = dimensions.score_market_dynamics(fred)
    contact = dimensions.score_contact_fit(lead.email, lead.company)

    breakdown = {
        "company_scale": co_scale.points,
        "buy_intent": buy_intent.points,
        "vertical_fit": vertical.points,
        "market_fit": market.points,
        "property_fit": property_.points,
        "market_dynamics": dynamics.points,
        "contact_fit": contact.points,
    }
    total = sum(breakdown.values())

    reasons: list[str] = []
    for dim_label, dim in [
        ("Company Scale", co_scale),
        ("Buy Intent", buy_intent),
        ("Vertical Fit", vertical),
        ("Market Fit", market),
        ("Property Fit", property_),
        ("Market Dynamics", dynamics),
        ("Contact Fit", contact),
    ]:
        for r in dim.reasons:
            reasons.append(f"[{dim_label}] {r}")

    # ----------- Disqualifier checks -----------
    disqualified = False
    disq_reason: str | None = None

    if vertical.meta.get("disqualified"):
        disqualified = True
        disq_reason = (
            f"Vertical disqualifier: {vertical.meta.get('vertical')} "
            f"(keyword: {vertical.meta.get('keyword')})"
        )

    if not _is_in_service_area(lead.country):
        disqualified = True
        if disq_reason is None:
            disq_reason = (
                f"Out of service area: country={lead.country} (EliseAI serves US/CA only)"
            )

    tier: Tier = compute_tier(total)
    if disqualified:
        tier = "Cold"

    return LeadScore(
        total=total,
        tier=tier,
        breakdown=breakdown,
        reasons=reasons,
        disqualified=disqualified,
        disqualifier_reason=disq_reason,
        meta={
            "vertical_meta": vertical.meta,
            "median_fallbacks": [
                k
                for k, dim in zip(
                    ["market_fit", "property_fit", "market_dynamics"],
                    [market, property_, dynamics],
                    strict=False,
                )
                if dim.meta.get("median_fallback")
            ],
        },
    )
