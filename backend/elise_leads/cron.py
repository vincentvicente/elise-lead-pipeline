"""Cron entry point — `python -m elise_leads.cron`.

Daily at 9am UTC, GitHub Actions invokes this module. It:
1. Creates a Run row (status='running')
2. Reads all pending leads, processes them via pipeline.process_one_lead
3. Aggregates outcomes, finalizes Run (status, counts, finished_at)
4. Generates the MD report and stores in runs.report_md
5. Sends alerts when triggered (pipeline_crash / all_leads_failed /
   high_failure_rate / no_pending_leads)

Outer-layer try/except (per PART_A v2 §10): if anything escapes pipeline,
we send the immediate `pipeline_crash` alert and exit non-zero so GH
Actions marks the workflow run failed.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
import uuid
from datetime import datetime, timezone

from elise_leads.alerting.client import send_alert
from elise_leads.alerting.reports import generate_run_report
from elise_leads.db import session_scope
from elise_leads.enrichers._http import close_http_client, log
from elise_leads.enrichers.orchestrator import EnrichmentOrchestrator
from elise_leads.models import Run
from elise_leads.pipeline import (
    LeadOutcome,
    fetch_pending_lead_ids,
    process_one_lead,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------
# Run lifecycle
# ----------------------------------------------------------------------------
async def _create_run() -> uuid.UUID:
    """Insert an empty Run row in 'running' state and return its id."""
    async with session_scope() as session:
        run = Run(
            started_at=_utcnow(),
            status="running",
            lead_count=0,
            success_count=0,
            failure_count=0,
        )
        session.add(run)
        await session.flush()  # populate run.id without committing
        run_id = run.id
    return run_id


async def _finalize_run(
    run_id: uuid.UUID, outcomes: list[LeadOutcome]
) -> Run:
    """Update the Run row with totals, status, finished_at, and report_md."""
    success = sum(1 for o in outcomes if o.status == "success")
    failure = sum(1 for o in outcomes if o.status == "failed")
    total = len(outcomes)

    if total == 0:
        status = "success"  # nothing to do = clean run
    elif failure == 0:
        status = "success"
    elif success == 0:
        status = "crashed"
    else:
        status = "partial"

    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            log.error("cron.finalize.run_missing", run_id=str(run_id))
            raise RuntimeError(f"Run {run_id} disappeared mid-flight")
        run.lead_count = total
        run.success_count = success
        run.failure_count = failure
        run.status = status
        run.finished_at = _utcnow()
        # Generate report inside the same session for query consistency
        run.report_md = await generate_run_report(session, run_id)
        log.info(
            "cron.run.finalized",
            run_id=str(run_id),
            status=status,
            success=success,
            failure=failure,
        )
        return run


# ----------------------------------------------------------------------------
# Alerting
# ----------------------------------------------------------------------------
async def _maybe_alert(run: Run, outcomes: list[LeadOutcome]) -> None:
    """Trigger alerts based on run state."""
    total = len(outcomes)
    success = sum(1 for o in outcomes if o.status == "success")
    failure = sum(1 for o in outcomes if o.status == "failed")

    if total == 0:
        async with session_scope() as session:
            await send_alert(
                session,
                alert_key="no_pending_leads",
                subject=f"Run {run.id}: no pending leads to process",
                body_md=(
                    f"# No pending leads\n\n"
                    f"Run `{run.id}` started at "
                    f"{run.started_at:%Y-%m-%d %H:%M UTC} found zero pending "
                    f"leads in the database. This is suppressed for 24h.\n"
                ),
            )
        return

    if total > 0 and success == 0:
        async with session_scope() as session:
            await send_alert(
                session,
                alert_key="all_leads_failed",
                subject=f"All {total} leads failed in run {run.id}",
                body_md=(
                    f"# 🚨 All {total} leads failed\n\n"
                    f"Run `{run.id}` processed {total} leads and **none** "
                    "succeeded. This usually means a global outage (DB, "
                    "Anthropic API, or all enrichers).\n\n"
                    f"- Run report: see runs.{run.id} in dashboard\n"
                    f"- Started: {run.started_at:%Y-%m-%d %H:%M UTC}\n"
                ),
            )
        return

    if failure / total > 0.30:
        async with session_scope() as session:
            await send_alert(
                session,
                alert_key="high_failure_rate",
                subject=f"Run {run.id}: {failure}/{total} leads failed ({failure / total:.0%})",
                body_md=(
                    f"# ⚠️ High failure rate\n\n"
                    f"Run `{run.id}` had **{failure}/{total} failures "
                    f"({failure / total:.0%})**. Investigate the dashboard "
                    f"for the run report.\n\n"
                    f"- Successes: {success}\n"
                    f"- Failures: {failure}\n"
                ),
            )


# ----------------------------------------------------------------------------
# Top-level entry
# ----------------------------------------------------------------------------
async def execute_run(run_id: uuid.UUID) -> Run:
    """Process all pending leads under an existing Run row.

    Shared by cron.run_pipeline_once() and the HTTP /runs/trigger endpoint.
    The trigger endpoint creates the Run synchronously, then schedules this
    function as a BackgroundTask so the HTTP response can return immediately
    with the new run_id.
    """
    log.info("cron.run.started", run_id=str(run_id))

    # Read pending lead IDs in a separate session
    async with session_scope() as session:
        pending_ids = await fetch_pending_lead_ids(session)

    log.info("cron.pending_count", run_id=str(run_id), count=len(pending_ids))

    # Process each lead — single shared orchestrator (httpx client reuse)
    orch = EnrichmentOrchestrator()
    outcomes: list[LeadOutcome] = []
    for lid in pending_ids:
        outcome = await process_one_lead(lid, run_id, orchestrator=orch)
        outcomes.append(outcome)

    # Finalize and alert
    run = await _finalize_run(run_id, outcomes)
    await _maybe_alert(run, outcomes)
    return run


async def run_pipeline_once() -> Run:
    """Execute one cron run end-to-end. Returns the finalized Run."""
    run_id = await _create_run()
    return await execute_run(run_id)


# Public re-export for routers/runs.py
async def create_run() -> uuid.UUID:
    """Public wrapper for HTTP /runs/trigger to grab a run_id synchronously."""
    return await _create_run()


async def main() -> int:
    """Entrypoint suitable for `python -m elise_leads.cron`.

    Returns the OS-exit code (0 for success / partial, 1 for crash).
    """
    try:
        run = await run_pipeline_once()
        # `success` and `partial` are both green-from-CI's-perspective.
        # `crashed` (zero successes) means GH Actions should mark failed.
        exit_code = 0 if run.status in {"success", "partial"} else 1
        return exit_code
    except Exception:  # noqa: BLE001
        # Outer-layer catch — pipeline-level crash, always P0 alert
        tb = traceback.format_exc()
        log.error("cron.pipeline_crash", traceback=tb)
        try:
            async with session_scope() as session:
                await send_alert(
                    session,
                    alert_key="pipeline_crash",
                    subject="EliseAI lead pipeline crashed (top-level)",
                    body_md=(
                        f"# 🚨 Pipeline crashed\n\n"
                        f"The cron pipeline raised an unhandled exception "
                        f"and could not finalize a Run row.\n\n"
                        f"## Traceback\n\n"
                        f"```\n{tb[-2000:]}\n```\n"
                    ),
                )
        except Exception:
            log.error("cron.crash_alert_failed", traceback=traceback.format_exc())
        return 1
    finally:
        await close_http_client()


def cli() -> None:
    """Sync wrapper for module-as-script invocation."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    cli()
