"""Top-level pipeline orchestration — process pending leads end-to-end.

For each lead:
1. Build LeadInput → run EnrichmentOrchestrator (M2)
2. Persist enriched + provenance + api_log rows
3. Score with rule-based rubric (M3)
4. Persist Score row
5. Select proof point (M4)
6. Generate email with 4-layer hallucination defense (M4)
7. Persist Email row + extra api_logs from Claude
8. Mark Lead.status = 'processed'

Failure handling — two-layer try/except per PART_A v2 §10:

  Outer layer (cron.py): catches everything, sends pipeline_crash alert
  Inner layer (per-lead, here): catches Lead-scoped errors, marks the
                                lead as failed, continues to next lead

Each lead runs in its own session/transaction so a single failure can't
poison the run-level state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.db import session_scope
from elise_leads.enrichers._http import log
from elise_leads.enrichers.base import LeadInput
from elise_leads.enrichers.orchestrator import (
    EnrichmentBundle,
    EnrichmentOrchestrator,
    persist_enrichment,
)
from elise_leads.generation.email import EmailDraft, generate_email
from elise_leads.generation.proof_points import select as select_proof_point
from elise_leads.models import ApiLog, Email, Lead, Score
from elise_leads.scoring.rubric import score as score_lead


@dataclass
class LeadOutcome:
    """Single-lead processing result returned to the caller."""

    lead_id: uuid.UUID
    status: str  # 'success' | 'failed'
    tier: str | None = None
    score_total: int | None = None
    email_source: str | None = None
    error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_input(lead: Lead) -> LeadInput:
    return LeadInput(
        name=lead.name,
        email=lead.email,
        company=lead.company,
        property_address=lead.property_address,
        city=lead.city,
        state=lead.state,
        country=lead.country,
    )


def _bundle_to_enriched_dict(bundle: EnrichmentBundle) -> dict[str, Any]:
    """Convert a bundle into the dict shape that scoring + proof-point
    selection expect (PART_A §10.x and §11.1).
    """
    return {
        "nmhc": bundle.nmhc.data,
        "wiki": bundle.wikipedia.data,
        "news": bundle.news.data,
        "walkscore": bundle.walkscore.data,
        "fred": bundle.fred.data,
        "census": _combine_census(bundle.geocoder.data, bundle.census_acs.data),
    }


def _combine_census(
    geo: dict[str, Any] | None, acs: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not geo and not acs:
        return None
    return {"geocoder": geo, "acs": acs}


# ----------------------------------------------------------------------------
# Per-lead processing
# ----------------------------------------------------------------------------
async def process_one_lead(
    lead_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    orchestrator: EnrichmentOrchestrator | None = None,
) -> LeadOutcome:
    """Process a single lead end-to-end with isolated session/transaction.

    Returns a LeadOutcome with status='success'|'failed'. Never raises —
    all exceptions are caught, logged, and reflected via outcome.error +
    Lead.status='failed' + Lead.error_message.
    """
    orch = orchestrator or EnrichmentOrchestrator()
    try:
        async with session_scope() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                return LeadOutcome(
                    lead_id=lead_id, status="failed", error="Lead not found"
                )

            # Mark processing + claim for this run
            lead.status = "processing"
            lead.run_id = run_id
            await session.flush()

            # 1. Enrichment
            lead_input = _to_input(lead)
            bundle = await orch.enrich(lead_input)
            await persist_enrichment(session, lead, bundle, run_id=run_id)

            # 2. Scoring
            enriched_dict = _bundle_to_enriched_dict(bundle)
            score_result = score_lead(lead_input, enriched_dict)
            session.add(
                Score(
                    lead_id=lead.id,
                    total=score_result.total,
                    tier=score_result.tier,
                    breakdown=score_result.breakdown,
                    reasons=score_result.reasons,
                )
            )

            # 3. Proof-point selection
            proof = select_proof_point(
                lead_company=lead_input.company,
                nmhc=bundle.nmhc.data,
                news=bundle.news.data,
                census=enriched_dict["census"],
            )

            # 4. Email generation
            facts = [
                (p.fact_key, p.fact_value, p.source, p.confidence)
                for p in bundle.all_provenance
            ]
            has_recent_news = bool(
                bundle.news.data and bundle.news.data.get("articles")
            )
            draft: EmailDraft = await generate_email(
                lead_name=lead_input.name,
                lead_email=lead_input.email,
                lead_company=lead_input.company,
                lead_property=lead_input.full_address,
                lead_city=lead_input.city,
                score=score_result,
                facts=facts,
                proof=proof,
                has_recent_news=has_recent_news,
            )

            # 5. Persist Email row
            session.add(
                Email(
                    lead_id=lead.id,
                    subject=draft.subject,
                    body=draft.body,
                    source=draft.source,
                    warnings=draft.warnings,
                    hallucination_check=draft.hallucination_check,
                    proof_point_used=draft.proof_point_used,
                )
            )

            # 6. Persist Claude API logs (each model attempt)
            for entry in draft.api_logs:
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

            # 7. Finalize
            lead.status = "processed"
            lead.processed_at = _utcnow()
            lead.error_message = None

            log.info(
                "pipeline.lead.success",
                lead_id=str(lead.id),
                tier=score_result.tier,
                score=score_result.total,
                email_source=draft.source,
            )
            return LeadOutcome(
                lead_id=lead.id,
                status="success",
                tier=score_result.tier,
                score_total=score_result.total,
                email_source=draft.source,
            )

    except Exception as exc:
        # Inner-layer catch: mark lead failed, keep running
        log.error(
            "pipeline.lead.failed",
            lead_id=str(lead_id),
            error=type(exc).__name__,
            detail=str(exc)[:300],
        )
        await _mark_lead_failed(lead_id, run_id, exc)
        return LeadOutcome(
            lead_id=lead_id, status="failed", error=str(exc)[:300]
        )


async def _mark_lead_failed(
    lead_id: uuid.UUID, run_id: uuid.UUID, exc: Exception
) -> None:
    """Open a fresh session to record the failure (the original may have
    been rolled back by session_scope after the exception).
    """
    try:
        async with session_scope() as session:
            lead = await session.get(Lead, lead_id)
            if lead is None:
                return
            lead.status = "failed"
            lead.run_id = run_id
            lead.error_message = f"{type(exc).__name__}: {str(exc)[:480]}"
    except Exception as inner:
        # Last-resort log; we're out of options here
        log.error(
            "pipeline.lead.mark_failed_failed",
            lead_id=str(lead_id),
            error=type(inner).__name__,
        )


# ----------------------------------------------------------------------------
# Run-level driver
# ----------------------------------------------------------------------------
async def fetch_pending_lead_ids(session: AsyncSession) -> list[uuid.UUID]:
    """Return IDs of leads in status='pending', oldest first."""
    rows = (
        await session.execute(
            select(Lead.id)
            .where(Lead.status == "pending")
            .order_by(Lead.uploaded_at)
        )
    ).all()
    return [row[0] for row in rows]
