"""Wikipedia enricher.

Pulls the lead-paragraph extract for the company (and optionally the
city). No API key required; Wikipedia just needs a polite User-Agent.

Provenance confidence is 0.70 — Wikipedia is crowd-sourced and may be
out-of-date, so the LLM prompt restricts it from citing Wikipedia
numbers verbatim (Layer 2 hallucination defense).

Also performs a lightweight regex scan for scale phrases like
"manages 50,000 units" to surface a structured signal back to scoring.
"""

from __future__ import annotations

import re
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

WIKI_API = "https://en.wikipedia.org/w/api.php"

# Scale phrase detection — captures e.g.
# "manages 800,000 apartment homes" / "managing over 100 properties" / "operates 50K units"
_SCALE_RE = re.compile(
    r"(?:manag\w*|operat\w*|owns|own\s|portfolio of|with|of)\b[\s\w,\-]*?"
    r"(\d{1,3}(?:,\d{3})+|\d{4,})\+?\s*(units|apartments|apartment homes|properties|communities|homes)",
    re.IGNORECASE,
)
_LARGEST_RE = re.compile(r"\b(largest|biggest|top \d+|fortune \d+)\b", re.IGNORECASE)


def _extract_scale(summary: str) -> dict[str, Any] | None:
    """Return {value: int, unit: str} if a scale phrase is found."""
    if not summary:
        return None
    m = _SCALE_RE.search(summary)
    if not m:
        return None
    raw_value, unit = m.group(1), m.group(2)
    try:
        value = int(raw_value.replace(",", ""))
    except ValueError:
        return None
    return {"value": value, "unit": unit.lower()}


def _extract_largest_claim(summary: str) -> str | None:
    if not summary:
        return None
    m = _LARGEST_RE.search(summary)
    return m.group(0) if m else None


@RETRY_ON_TRANSIENT
async def _fetch_extract(
    client: httpx.AsyncClient, title: str
) -> tuple[int, dict[str, Any]]:
    """Fetch the lead extract for a title. Returns (status, json)."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "exintro": "true",
        "explaintext": "true",
        "inprop": "url",
        "redirects": "1",
        "titles": title,
    }
    resp = await client.get(WIKI_API, params=params)
    return resp.status_code, resp.json()


def _parse_pages(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Wikipedia returns query.pages keyed by page id (or '-1' for missing).

    Returns None if the page does not exist.
    """
    pages = (payload or {}).get("query", {}).get("pages") or {}
    if not pages:
        return None
    page = next(iter(pages.values()))
    if "missing" in page or page.get("pageid") in (None, -1):
        return None
    return {
        "title": page.get("title"),
        "url": page.get("fullurl"),
        "summary": (page.get("extract") or "").strip()[:1500],
    }


class WikipediaEnricher:
    name = "wikipedia"

    async def enrich(self, lead: LeadInput, **kwargs: Any) -> EnrichmentResult:
        client = get_http_client()
        async with timed_call(self.name) as ctx:
            try:
                status, payload = await _fetch_extract(client, lead.company)
                ctx["status"] = status
                ctx["success"] = status == 200
                if status != 200:
                    ctx["error_type"] = classify_http_error(Exception(), status)
                    return EnrichmentResult(
                        data=None,
                        api_log=ctx["api_log"],
                        error=ctx["error_type"],
                    )

                company_page = _parse_pages(payload)

                # Fetch city page in parallel? Skipped for simplicity — one
                # extra round-trip on a no-key, no-rate-limit endpoint is fine.
                city_title = f"{lead.city}, {lead.state}"
                city_status, city_payload = await _fetch_extract(client, city_title)
                city_page = _parse_pages(city_payload) if city_status == 200 else None

            except Exception as exc:
                ctx["error_type"] = classify_http_error(exc)
                ctx["error_detail"] = str(exc)[:500]
                log.warning(
                    "wikipedia.enrich.failed",
                    company=lead.company,
                    error=ctx["error_type"],
                )
                return EnrichmentResult(
                    data=None,
                    api_log=ctx["api_log"] if ctx.get("api_log") else None,
                    error=ctx["error_type"],
                )

        # Build data + provenance
        data: dict[str, Any] = {
            "company_page": company_page,
            "city_page": city_page,
        }

        provenance: list[ProvenanceFact] = []

        if company_page is not None:
            provenance.append(
                ProvenanceFact(
                    fact_key="wikipedia_company_exists",
                    fact_value=True,
                    source="wikipedia_2026",
                    confidence=0.85,  # existence is high-confidence
                )
            )

            scale = _extract_scale(company_page["summary"])
            if scale is not None:
                data["company_scale_extracted"] = scale
                provenance.append(
                    ProvenanceFact(
                        # Lower confidence — text-extracted, may be stale
                        fact_key="company_scale_text_extracted",
                        fact_value=scale,
                        source="wikipedia_2026",
                        confidence=0.65,
                    )
                )

            largest = _extract_largest_claim(company_page["summary"])
            if largest:
                data["company_largest_claim"] = largest
                provenance.append(
                    ProvenanceFact(
                        fact_key="company_largest_claim",
                        fact_value=largest,
                        source="wikipedia_2026",
                        confidence=0.65,
                    )
                )

        if city_page is not None:
            provenance.append(
                ProvenanceFact(
                    fact_key="city_summary",
                    fact_value=city_page["summary"][:500],
                    source="wikipedia_2026",
                    confidence=0.70,
                )
            )

        return EnrichmentResult(
            data=data,
            provenance=provenance,
            api_log=ctx["api_log"],
        )
