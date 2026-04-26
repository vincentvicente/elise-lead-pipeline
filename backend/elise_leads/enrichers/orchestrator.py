"""Enrichment orchestrator — runs all enrichers for one lead.

Execution graph (PART_A §3.3):
- Group 1 (independent): NMHC + Wikipedia + News + FRED — run concurrently
- Group 2 (gates Group 3): Census Geocoder
- Group 3 (depends on geocoder): Census ACS + WalkScore — run concurrently

Each enricher returns an EnrichmentResult. The orchestrator gathers all
results into an `EnrichmentBundle` and writes:
- One EnrichedData row (with per-source JSON + errors map)
- N Provenance rows (one per fact)
- N ApiLog rows (one per actual external call)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.enrichers._http import log
from elise_leads.enrichers.base import (
    EnrichmentResult,
    LeadInput,
    ProvenanceFact,
)
from elise_leads.enrichers.census_acs import CensusAcsEnricher
from elise_leads.enrichers.census_geocoder import CensusGeocoderEnricher
from elise_leads.enrichers.fred import FredEnricher
from elise_leads.enrichers.news import NewsApiEnricher
from elise_leads.enrichers.nmhc import NmhcEnricher
from elise_leads.enrichers.walkscore import WalkScoreEnricher
from elise_leads.enrichers.wikipedia import WikipediaEnricher
from elise_leads.models import ApiLog, EnrichedData, Lead, Provenance


@dataclass
class EnrichmentBundle:
    """Aggregated results from all enrichers for one lead."""

    nmhc: EnrichmentResult
    wikipedia: EnrichmentResult
    news: EnrichmentResult
    fred: EnrichmentResult
    geocoder: EnrichmentResult
    census_acs: EnrichmentResult
    walkscore: EnrichmentResult

    @property
    def all_results(self) -> dict[str, EnrichmentResult]:
        return {
            "nmhc": self.nmhc,
            "wikipedia": self.wikipedia,
            "news": self.news,
            "fred": self.fred,
            "census_geocoder": self.geocoder,
            "census_acs": self.census_acs,
            "walkscore": self.walkscore,
        }

    @property
    def errors_map(self) -> dict[str, str]:
        return {
            name: r.error
            for name, r in self.all_results.items()
            if r.error is not None
        }

    @property
    def all_provenance(self) -> list[ProvenanceFact]:
        out: list[ProvenanceFact] = []
        for r in self.all_results.values():
            out.extend(r.provenance)
        return out

    @property
    def all_api_logs(self) -> list:
        return [r.api_log for r in self.all_results.values() if r.api_log is not None]


class EnrichmentOrchestrator:
    """Runs the full enrichment graph for one lead.

    Enrichers are constructed once at orchestrator init (so settings are
    cached), then reused across leads.
    """

    def __init__(self) -> None:
        self.nmhc = NmhcEnricher()
        self.wikipedia = WikipediaEnricher()
        self.news = NewsApiEnricher()
        self.fred = FredEnricher()
        self.geocoder = CensusGeocoderEnricher()
        self.census_acs = CensusAcsEnricher()
        self.walkscore = WalkScoreEnricher()

    async def enrich(self, lead: LeadInput) -> EnrichmentBundle:
        """Execute the full enrichment graph and return the bundle."""

        # Group 1: independent enrichers (no upstream deps)
        # Group 2: geocoder (gates Group 3)
        # Run Group 1 + Group 2 concurrently; Group 3 waits on Group 2.
        group1_task = asyncio.gather(
            self.nmhc.enrich(lead),
            self.wikipedia.enrich(lead),
            self.news.enrich(lead),
            self.fred.enrich(lead),
            return_exceptions=False,
        )
        geocoder_task = asyncio.create_task(self.geocoder.enrich(lead))

        # Wait for geocoder (Group 3 depends on it)
        geo_result = await geocoder_task

        # Group 3 — depends on geocoder output
        geo_payload = geo_result.data if geo_result.succeeded else None
        acs_coro = self.census_acs.enrich(lead, geocode=geo_payload)
        ws_coro = self.walkscore.enrich(lead, geocode=geo_payload)

        # Wait for everything else
        nmhc_r, wiki_r, news_r, fred_r = await group1_task
        acs_r, ws_r = await asyncio.gather(acs_coro, ws_coro)

        return EnrichmentBundle(
            nmhc=nmhc_r,
            wikipedia=wiki_r,
            news=news_r,
            fred=fred_r,
            geocoder=geo_result,
            census_acs=acs_r,
            walkscore=ws_r,
        )


# ----------------------------------------------------------------------------
# Persistence helper — writes a bundle to the DB
# ----------------------------------------------------------------------------
async def persist_enrichment(
    session: AsyncSession,
    lead: Lead,
    bundle: EnrichmentBundle,
    run_id: uuid.UUID | None = None,
) -> EnrichedData:
    """Write the EnrichedData row, all Provenance rows, and all ApiLog rows.

    Caller is responsible for `session.commit()`.
    """
    # 1. EnrichedData
    enriched = EnrichedData(
        lead_id=lead.id,
        nmhc_json=bundle.nmhc.data,
        wiki_json=bundle.wikipedia.data,
        news_json=bundle.news.data,
        fred_json=bundle.fred.data,
        census_json=_combine_census(bundle.geocoder, bundle.census_acs),
        walkscore_json=bundle.walkscore.data,
        errors=bundle.errors_map,
    )
    session.add(enriched)

    # 2. Provenance rows
    for fact in bundle.all_provenance:
        session.add(
            Provenance(
                lead_id=lead.id,
                fact_key=fact.fact_key,
                fact_value=fact.fact_value,
                source=fact.source,
                confidence=fact.confidence,
                fetched_at=datetime.now(timezone.utc),
                raw_ref=fact.raw_ref,
            )
        )

    # 3. ApiLog rows
    for entry in bundle.all_api_logs:
        session.add(
            ApiLog(
                run_id=run_id,
                lead_id=lead.id,
                api_name=entry.api_name,
                started_at=entry.started_at,
                duration_ms=entry.duration_ms,
                http_status=entry.http_status,
                success=entry.success,
                error_type=entry.error_type,
                error_detail=entry.error_detail,
            )
        )

    log.info(
        "enrichment.persisted",
        lead_id=str(lead.id),
        provenance_count=len(bundle.all_provenance),
        api_log_count=len(bundle.all_api_logs),
        errors=list(bundle.errors_map.keys()),
    )

    return enriched


def _combine_census(
    geo: EnrichmentResult, acs: EnrichmentResult
) -> dict[str, Any] | None:
    """Combine Census Geocoder + ACS into a single census_json blob."""
    out: dict[str, Any] = {}
    if geo.data:
        out["geocoder"] = geo.data
    if acs.data:
        out["acs"] = acs.data
    return out or None
