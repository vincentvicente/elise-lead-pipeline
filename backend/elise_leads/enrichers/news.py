"""NewsAPI enricher.

Fetches the most recent ~30 days of articles mentioning the company.
Free tier is 100 req/day, so we cache by company name (multiple leads
from the same operator share results).

Per the design (PART_A §9.2), we deliberately do NOT include industry
keywords in the query — that loses recall on M&A headlines like
"Greystar acquires Alliance Residential" where "apartment" doesn't
appear in the title. Instead we score relevance post-fetch.

Confidence:
- 0.85 — articles from premium sources (WSJ, Bloomberg, Reuters, etc.)
- 0.70 — other sources
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

NEWS_URL = "https://newsapi.org/v2/everything"

PREMIUM_SOURCES = {
    "Wall Street Journal",
    "Bloomberg",
    "Reuters",
    "Financial Times",
    "Forbes",
    "The New York Times",
    "Business Insider",
    "CNBC",
    "Real Deal",
}

# Tier-1 buy-intent signal keywords (matches PART_A §10.2 Buy Intent rubric).
# Use word stems so verb conjugations all match (e.g. "acquir" → acquires/
# acquired/acquiring/acquisition).
SIGNAL_KEYWORDS = {
    "high": ["acquir", "merger", "merges", "merged"],
    "medium_high": ["expansion", "expand", "launch", "new property", "groundbreaking"],
    "medium": ["funding", "raise", "series ", "investment"],
    "low": ["partnership", "partnered", "technology", "platform"],
}

# Industry relevance tokens for post-filter scoring (PART_A §9.2)
INDUSTRY_TOKENS = {
    "apartment", "apartments", "residential", "housing", "multifamily",
    "property", "properties", "leasing", "rental", "real estate", "REIT",
}

# Per-company-name cache; key = company name lowercased.
_NEWS_CACHE: dict[str, dict[str, Any]] = {}


@RETRY_ON_TRANSIENT
async def _fetch_news(
    client: httpx.AsyncClient, company: str, api_key: str
) -> tuple[int, dict[str, Any]]:
    from_dt = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    params = {
        "q": f'"{company}"',
        "from": from_dt,
        "sortBy": "relevancy",
        "language": "en",
        "pageSize": "20",
        "apiKey": api_key,
    }
    resp = await client.get(NEWS_URL, params=params, timeout=15.0)
    return resp.status_code, resp.json()


def _score_relevance(article: dict[str, Any]) -> float:
    """0.0–1.0 score for how 'real-estate-related' an article is."""
    text = (
        (article.get("title") or "")
        + " "
        + (article.get("description") or "")
    ).lower()
    hits = sum(1 for tok in INDUSTRY_TOKENS if tok in text)
    return min(hits / 3.0, 1.0)  # cap at 1.0; 3+ tokens = max relevance


def _detect_signal_keywords(articles: list[dict]) -> dict[str, list[str]]:
    """Map signal tier → list of headlines that triggered it."""
    found: dict[str, list[str]] = {k: [] for k in SIGNAL_KEYWORDS}
    for art in articles:
        text = ((art.get("title") or "") + " " + (art.get("description") or "")).lower()
        for tier, kws in SIGNAL_KEYWORDS.items():
            for kw in kws:
                if kw in text:
                    found[tier].append(art.get("title", ""))
                    break
    # Drop empty tiers
    return {k: v for k, v in found.items() if v}


def _normalize_articles(raw: list[dict]) -> list[dict[str, Any]]:
    """Keep only the fields we actually use; drop garbage articles."""
    out: list[dict[str, Any]] = []
    for a in raw:
        if not a.get("title") or a.get("title") == "[Removed]":
            continue
        out.append(
            {
                "title": a.get("title"),
                "description": a.get("description") or "",
                "url": a.get("url"),
                "source": (a.get("source") or {}).get("name") or "Unknown",
                "published_at": a.get("publishedAt"),
                "relevance_score": round(_score_relevance(a), 2),
            }
        )
    # Sort by relevance × premium-source boost, take top 5
    out.sort(
        key=lambda a: (a["relevance_score"], a["source"] in PREMIUM_SOURCES),
        reverse=True,
    )
    return out[:5]


class NewsApiEnricher:
    name = "newsapi"

    def __init__(self) -> None:
        self.api_key = get_settings().news_api_key

    async def enrich(self, lead: LeadInput, **kwargs: Any) -> EnrichmentResult:
        if not self.api_key:
            return EnrichmentResult(
                data=None, api_log=None, error="missing_api_key"
            )

        cache_key = lead.company.strip().lower()
        if cache_key in _NEWS_CACHE:
            cached = _NEWS_CACHE[cache_key]
            return EnrichmentResult(
                data={**cached, "cached": True},
                provenance=_provenance_facts(cached),
                api_log=None,
            )

        client = get_http_client()
        async with timed_call(self.name) as ctx:
            try:
                status, payload = await _fetch_news(client, lead.company, self.api_key)
                ctx["status"] = status

                # 426 = upgrade required, 429 = rate-limited
                if status == 426 or status == 429:
                    ctx["error_type"] = "rate_limit" if status == 429 else "quota_exceeded"
                    return EnrichmentResult(
                        data=None, api_log=ctx["api_log"], error=ctx["error_type"]
                    )
                if status != 200:
                    ctx["error_type"] = classify_http_error(Exception(), status)
                    return EnrichmentResult(
                        data=None, api_log=ctx["api_log"], error=ctx["error_type"]
                    )

                articles_raw = (payload or {}).get("articles") or []
                articles = _normalize_articles(articles_raw)
                signal_keywords = _detect_signal_keywords(articles)
                ctx["success"] = True

                data = {
                    "total_results": (payload or {}).get("totalResults", 0),
                    "articles": articles,
                    "signal_keywords": signal_keywords,
                    "premium_count": sum(
                        1 for a in articles if a["source"] in PREMIUM_SOURCES
                    ),
                }

            except Exception as exc:
                ctx["error_type"] = classify_http_error(exc)
                ctx["error_detail"] = str(exc)[:500]
                log.warning("newsapi.failed", error=ctx["error_type"])
                return EnrichmentResult(
                    data=None, api_log=ctx.get("api_log"), error=ctx["error_type"]
                )

        _NEWS_CACHE[cache_key] = data
        return EnrichmentResult(
            data=data, provenance=_provenance_facts(data), api_log=ctx["api_log"]
        )


def _provenance_facts(data: dict[str, Any]) -> list[ProvenanceFact]:
    facts: list[ProvenanceFact] = []
    for art in data.get("articles", [])[:3]:
        confidence = 0.85 if art["source"] in PREMIUM_SOURCES else 0.70
        facts.append(
            ProvenanceFact(
                fact_key=f"news_headline_{art['published_at']}",
                fact_value={
                    "title": art["title"],
                    "url": art["url"],
                    "source": art["source"],
                    "published_at": art["published_at"],
                },
                source=f"newsapi_{art['source'].lower().replace(' ', '_')}",
                confidence=confidence,
            )
        )
    if data.get("signal_keywords"):
        facts.append(
            ProvenanceFact(
                fact_key="news_buy_intent_signals",
                fact_value=list(data["signal_keywords"].keys()),
                source="newsapi_keyword_extraction",
                confidence=0.80,
            )
        )
    return facts


def clear_cache() -> None:
    _NEWS_CACHE.clear()
