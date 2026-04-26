"""Rule-based insights extraction.

Produces 3–5 plain-English bullets summarizing the most relevant signals
for the SDR. Shown in the dashboard alongside the lead detail view.

Rules-based (not LLM) for three reasons:
1. Deterministic — same enrichment always produces same insights
2. Free — no token cost
3. Easy to audit — each insight maps to a specific signal
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _days_ago(iso_ts: str) -> int | None:
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    delta = datetime.now(timezone.utc) - ts
    return max(0, delta.days)


def extract(
    *,
    lead_company: str,
    nmhc: dict[str, Any] | None,
    wiki: dict[str, Any] | None,
    news: dict[str, Any] | None,
    census: dict[str, Any] | None,
    walkscore: dict[str, Any] | None,
    fred: dict[str, Any] | None,
    score_tier: str,
    score_total: int,
) -> list[str]:
    """Return 3–5 insight bullets (most important first)."""
    bullets: list[str] = []

    # 1. Score headline
    bullets.append(f"Lead score: {score_total}/100 ({score_tier} tier)")

    # 2. Company scale signal (highest priority for ICP fit)
    if nmhc and nmhc.get("matched"):
        rank = nmhc["rank"]
        units = nmhc.get("units_managed", 0)
        bullets.append(
            f"{lead_company} is NMHC Top {50 if rank > 10 else 10} "
            f"(rank #{rank}, {units:,} units managed)"
        )
    elif wiki and (wiki.get("company_page") or {}).get("title"):
        scale = wiki.get("company_scale_extracted")
        if scale:
            bullets.append(
                f"Wikipedia indicates ~{scale['value']:,} {scale['unit']}"
            )
        else:
            bullets.append(
                "Has Wikipedia presence — established but unranked operator"
            )

    # 3. Buy-intent signal — most recent relevant news
    if news and news.get("articles"):
        top = news["articles"][0]  # already sorted by relevance
        days = _days_ago(top.get("published_at", ""))
        date_phrase = (
            f"({days} days ago)" if days is not None else "(recent)"
        )
        title = top.get("title", "").strip()
        # Truncate very long headlines
        if len(title) > 90:
            title = title[:87] + "..."
        bullets.append(f"Recent news: \"{title}\" {date_phrase} — {top.get('source', 'Unknown')}")

    # 4. Market characteristic — pick the most striking
    if census and (census.get("acs") or {}):
        acs = census["acs"]
        renter = acs.get("renter_pct")
        if renter and renter > 0.6:
            bullets.append(
                f"Property tract is {renter * 100:.0f}% renter-occupied — strong ICP match"
            )
        elif renter and renter < 0.35:
            bullets.append(
                f"Property tract is owner-dominant ({renter * 100:.0f}% renters)"
            )

    # 5. Property/walkability characterization (Class A signal)
    if walkscore and walkscore.get("walk_score") is not None:
        ws = walkscore["walk_score"]
        if ws >= 80:
            bullets.append(
                f"Walk Score {ws} ({walkscore.get('walk_description', '')}) — urban core"
            )
        elif ws < 30:
            bullets.append(
                f"Walk Score {ws} (car-dependent) — suburban/rural location"
            )

    # 6. Market-pressure signal from FRED (only if striking)
    if fred and fred.get("vacancy_rate_pct") is not None:
        vac = fred["vacancy_rate_pct"]
        if vac > 7:
            bullets.append(
                f"Local rental vacancy {vac}% — high leasing pressure"
            )

    # Cap at 5 bullets to keep dashboard scannable
    return bullets[:5]
