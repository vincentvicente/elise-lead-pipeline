"""Scoring dimension functions.

Each function takes the relevant enriched data (or raw lead fields) and
returns a `DimensionResult` with:
- points (int)
- reasons (human-readable bullets shown to SDRs)
- max_points (the dimension's ceiling, used for missing-data median fallback)
- meta (optional structured info, e.g. disqualifier flags)

Mapping from PART_A v2 §10.2:

| Dimension       | Max | Source                      |
|-----------------|-----|-----------------------------|
| Company Scale   | 25  | NMHC + Wikipedia + News     |
| Buy Intent      | 20  | News keyword tier           |
| Vertical Fit    | 10  | Lead.company keywords       |
| Market Fit      | 15  | Census ACS                  |
| Property Fit    | 10  | WalkScore + Census rent     |
| Market Dynamics |  5  | FRED                        |
| Contact Fit     | 15  | Lead email                  |
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DimensionResult:
    points: int
    max_points: int
    reasons: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def median_fallback(self, reason: str = "data unavailable") -> "DimensionResult":
        """Return a copy with median points + a 'missing data' reason.

        Used when the upstream API failed entirely. We do NOT penalize
        the lead — give the median half-of-max so a great lead with
        flaky API isn't unfairly buried in Cold.
        """
        return DimensionResult(
            points=self.max_points // 2,
            max_points=self.max_points,
            reasons=[f"{reason} (median fallback)"],
            meta={"median_fallback": True},
        )


# ============================================================================
# Company-side dimensions
# ============================================================================


def score_company_scale(
    nmhc: dict[str, Any] | None,
    wiki: dict[str, Any] | None,
    news: dict[str, Any] | None,
) -> DimensionResult:
    """Company Scale (max 25)."""
    points = 0
    reasons: list[str] = []

    # NMHC match — strongest signal
    if nmhc and nmhc.get("matched"):
        rank = nmhc.get("rank", 999)
        units = nmhc.get("units_managed", 0)
        if rank <= 10:
            points += 15
            reasons.append(
                f"NMHC Top 10 operator (#{rank}, {units:,} units managed)"
            )
        else:
            points += 10
            reasons.append(f"NMHC Top 50 operator (#{rank}, {units:,} units)")

    # Wikipedia presence + scale extracted
    if wiki and wiki.get("company_page"):
        scale = wiki.get("company_scale_extracted")
        if scale and scale.get("value"):
            points += 5
            reasons.append(
                f"Wikipedia indicates {scale['value']:,} {scale['unit']}"
            )
        else:
            points += 2
            reasons.append("Has Wikipedia presence (likely established operator)")

    # News volume + premium source bonus
    if news and news.get("articles"):
        article_count = len(news["articles"])
        premium_count = news.get("premium_count", 0)
        if article_count >= 5 or premium_count >= 2:
            points += 5
            reasons.append(
                f"Strong media presence ({article_count} articles, {premium_count} premium sources)"
            )
        elif article_count >= 2:
            points += 3
            reasons.append(f"Moderate media coverage ({article_count} articles)")
        else:
            points += 1

    return DimensionResult(
        points=min(points, 25),
        max_points=25,
        reasons=reasons,
    )


def score_buy_intent(news: dict[str, Any] | None) -> DimensionResult:
    """Buy Intent (max 20). Tiered by strongest signal keyword."""
    if not news or not news.get("articles"):
        return DimensionResult(
            points=5,  # legitimate "no news" baseline (not zero)
            max_points=20,
            reasons=["No recent company news (small or quiet operator)"],
        )

    signals: dict[str, list[str]] = news.get("signal_keywords") or {}
    # Order matters — strongest first
    if "high" in signals:
        sample = signals["high"][0] if signals["high"] else ""
        return DimensionResult(
            points=20,
            max_points=20,
            reasons=[f"Strong buy signal — M&A in news: '{sample[:80]}'"],
        )
    if "medium_high" in signals:
        sample = signals["medium_high"][0] if signals["medium_high"] else ""
        return DimensionResult(
            points=18,
            max_points=20,
            reasons=[f"Expansion signal — '{sample[:80]}'"],
        )
    if "medium" in signals:
        sample = signals["medium"][0] if signals["medium"] else ""
        return DimensionResult(
            points=15,
            max_points=20,
            reasons=[f"Funding signal — '{sample[:80]}'"],
        )
    if "low" in signals:
        return DimensionResult(
            points=12,
            max_points=20,
            reasons=["Tech/partnership signal in news"],
        )

    # Has news but no targeted keywords
    return DimensionResult(
        points=10,
        max_points=20,
        reasons=[f"Generic media coverage ({len(news['articles'])} articles)"],
    )


# Vertical Fit — also acts as hard disqualifier for senior/commercial
VERTICAL_KEYWORDS = {
    "multifamily": ["apartment", "multifamily", "residential", "rental community"],
    "student": ["student", "campus", "university housing", "college housing"],
    "affordable": ["affordable", "lihtc", "section 8", "housing authority"],
    "military": ["military housing", "military family", "naval housing"],
    "sfr": ["single family rental", "build-to-rent", "build to rent", " btr "],
}

DISQUALIFIER_KEYWORDS = {
    "senior": ["senior living", "55+", "active adult", "retirement community", "assisted living"],
    "commercial": [
        "office building",
        "retail real estate",
        "industrial real estate",
        "commercial real estate",
        "commercial property",
    ],
}


def score_vertical_fit(
    company_name: str, wiki_summary: str | None = None
) -> DimensionResult:
    """Vertical Fit (max 10) — also flags hard disqualifiers."""
    text = company_name.lower()
    if wiki_summary:
        text += " " + wiki_summary.lower()

    # Check disqualifiers first — these set tier to Cold regardless of points
    for vertical, keywords in DISQUALIFIER_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return DimensionResult(
                    points=0,
                    max_points=10,
                    reasons=[
                        f"⚠ Out-of-ICP vertical detected ('{kw}'): "
                        f"{vertical} — disqualified"
                    ],
                    meta={"disqualified": True, "vertical": vertical, "keyword": kw},
                )

    # Check positive matches
    for vertical, keywords in VERTICAL_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return DimensionResult(
                    points=10,
                    max_points=10,
                    reasons=[f"Clear {vertical} vertical fit (keyword: '{kw.strip()}')"],
                    meta={"vertical": vertical, "keyword": kw.strip()},
                )

    # No clear signal — neutral midpoint, not penalized
    return DimensionResult(
        points=5,
        max_points=10,
        reasons=["Vertical not clearly identifiable — assumed multifamily by default"],
    )


# ============================================================================
# Geography dimensions
# ============================================================================


def score_market_fit(census: dict[str, Any] | None) -> DimensionResult:
    """Market Fit (max 15) — Census ACS demographics."""
    if not census or not census.get("acs"):
        return DimensionResult(points=0, max_points=15).median_fallback(
            "Census ACS unavailable"
        )

    acs = census["acs"]
    points = 0
    reasons: list[str] = []

    # Renter % (8 max)
    renter_pct = acs.get("renter_pct")
    if renter_pct is not None:
        pct = renter_pct * 100
        if renter_pct > 0.65:
            points += 8
            reasons.append(f"High renter density ({pct:.0f}%) — strong ICP fit")
        elif renter_pct > 0.50:
            points += 5
            reasons.append(f"Moderate renter density ({pct:.0f}%)")
        elif renter_pct > 0.35:
            points += 3
            reasons.append(f"Low-moderate renter density ({pct:.0f}%)")
        else:
            points += 1
            reasons.append(f"Owner-dominant area ({pct:.0f}% renters)")

    # Median income (7 max)
    income = acs.get("median_household_income")
    if income is not None:
        if income > 75_000:
            points += 7
            reasons.append(f"High median income (${income:,}) — Class A market")
        elif income > 55_000:
            points += 5
            reasons.append(f"Mid-tier income (${income:,})")
        elif income > 40_000:
            points += 3
            reasons.append(f"Working-class market (${income:,} median)")
        else:
            points += 1
            reasons.append(f"Below-median income (${income:,})")

    return DimensionResult(points=min(points, 15), max_points=15, reasons=reasons)


def score_property_fit(
    walkscore: dict[str, Any] | None, census: dict[str, Any] | None
) -> DimensionResult:
    """Property Fit (max 10) — WalkScore + Census median rent."""
    points = 0
    reasons: list[str] = []
    has_data = False

    # WalkScore (5 max)
    if walkscore and walkscore.get("walk_score") is not None:
        has_data = True
        ws = walkscore["walk_score"]
        desc = walkscore.get("walk_description", "")
        if ws > 80:
            points += 5
            reasons.append(f"Walk Score {ws} ({desc}) — urban core")
        elif ws > 60:
            points += 4
            reasons.append(f"Walk Score {ws} ({desc})")
        elif ws > 40:
            points += 2
            reasons.append(f"Walk Score {ws} (moderate)")
        else:
            points += 1
            reasons.append(f"Walk Score {ws} (car-dependent)")

    # Median rent (5 max)
    if census and census.get("acs", {}).get("median_monthly_rent") is not None:
        has_data = True
        rent = census["acs"]["median_monthly_rent"]
        if rent > 1500:
            points += 5
            reasons.append(f"High rent market (${rent:,}/mo)")
        elif rent > 1000:
            points += 3
            reasons.append(f"Mid rent market (${rent:,}/mo)")
        else:
            points += 1
            reasons.append(f"Affordable rent (${rent:,}/mo)")

    if not has_data:
        return DimensionResult(points=0, max_points=10).median_fallback(
            "Property data unavailable"
        )

    return DimensionResult(points=min(points, 10), max_points=10, reasons=reasons)


def score_market_dynamics(fred: dict[str, Any] | None) -> DimensionResult:
    """Market Dynamics (max 5) — FRED vacancy + rent YoY."""
    if not fred or fred.get("vacancy_rate_pct") is None:
        return DimensionResult(points=0, max_points=5).median_fallback(
            "FRED data unavailable"
        )

    points = 0
    reasons: list[str] = []

    # Vacancy rate (3 max — high vacancy = more leasing pressure)
    vac = fred["vacancy_rate_pct"]
    if vac > 7:
        points += 3
        reasons.append(f"High vacancy ({vac}%) — strong leasing pressure")
    elif vac > 5:
        points += 2
        reasons.append(f"Moderate vacancy ({vac}%)")
    else:
        points += 1
        reasons.append(f"Tight market ({vac}% vacancy)")

    # Rent YoY (2 max)
    yoy = fred.get("rent_yoy_pct")
    if yoy is not None:
        if yoy > 5:
            points += 2
            reasons.append(f"Strong rent growth ({yoy:+.1f}% YoY)")
        elif yoy > 0:
            points += 1
            reasons.append(f"Positive rent growth ({yoy:+.1f}% YoY)")
        else:
            reasons.append(f"Flat/declining rent ({yoy:+.1f}% YoY)")

    return DimensionResult(points=min(points, 5), max_points=5, reasons=reasons)


# ============================================================================
# Contact-side dimension
# ============================================================================

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "aol.com",
    "protonmail.com",
}

GENERIC_PREFIXES = {
    "info",
    "contact",
    "hello",
    "admin",
    "sales",
    "support",
    "team",
    "no-reply",
    "noreply",
    "leasing",
    "marketing",
    "general",
}

# Pattern hints that suggest a third-party advisor / consultant, not a
# direct employee. Kept short and precise to avoid false positives.
CONSULTANT_DOMAIN_HINTS = (
    "advisors",
    "advisory",
    "consulting",
    "partners",
    "ventures",
    "capital",
)


def _domain_matches_company(domain: str, company: str) -> str:
    """Return one of: 'match' / 'consultant' / 'mismatch'."""
    domain_root = re.sub(r"\.(com|org|net|co|io|us)$", "", domain.lower())
    domain_root = domain_root.replace("-", "").replace(".", "")

    company_clean = re.sub(r"[^a-z0-9]", "", company.lower())

    # 4+ char overlap counts as a match
    if domain_root in company_clean and len(domain_root) >= 4:
        return "match"
    if company_clean in domain_root and len(company_clean) >= 4:
        return "match"

    # Consultant hint — domain looks like an advisor firm
    if any(hint in domain_root for hint in CONSULTANT_DOMAIN_HINTS):
        return "consultant"

    return "mismatch"


def score_contact_fit(email: str, company: str) -> DimensionResult:
    """Contact Fit (max 15)."""
    points = 0
    reasons: list[str] = []

    if "@" not in email:
        return DimensionResult(
            points=0, max_points=15, reasons=["Invalid email format"]
        )

    prefix, domain = email.lower().rsplit("@", 1)

    # 1. Corporate domain (5)
    if domain in FREE_EMAIL_DOMAINS:
        reasons.append(f"Free email domain ({domain}) — likely individual or small operator")
    else:
        points += 5
        reasons.append(f"Corporate email domain ({domain})")

    # 2. Domain ↔ company match (5)
    if domain not in FREE_EMAIL_DOMAINS:
        match_type = _domain_matches_company(domain, company)
        if match_type == "match":
            points += 5
            reasons.append(f"Email domain matches company name ({domain} ≈ {company})")
        elif match_type == "consultant":
            points += 2
            reasons.append(
                f"Domain looks like advisor/consultant ({domain}) — verify true buyer"
            )
        else:
            reasons.append(f"Email domain ({domain}) doesn't match company name")

    # 3. Prefix shape (5)
    if prefix in GENERIC_PREFIXES:
        reasons.append(f"Generic inbox '{prefix}@' — not a personal contact")
    elif "." in prefix or "_" in prefix:
        points += 5
        reasons.append("Personal-format email (firstname.lastname pattern)")
    else:
        points += 3
        reasons.append("Single-token prefix — likely personal but ambiguous")

    return DimensionResult(points=min(points, 15), max_points=15, reasons=reasons)
