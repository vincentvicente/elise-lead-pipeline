"""Run report generation — markdown summary persisted to runs.report_md.

Two consumers:
1. Dashboard `/runs/:id` page renders this in a markdown viewer
2. Alert email body when high failure rate triggers a notification

The report aggregates from api_logs, scores, and emails for the run, so
it's most accurate when called AFTER all per-lead sessions have flushed.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.models import ApiLog, Email, Lead, Run, Score


def _fmt_time(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100) * (len(s) - 1)))))
    return s[k]


async def generate_run_report(session: AsyncSession, run_id: uuid.UUID) -> str:
    """Render a markdown run report from the persisted run/leads/logs."""
    run = await session.get(Run, run_id)
    if run is None:
        return f"# Run {run_id}\n\nRun not found."

    # Tier counts
    tier_rows = (
        await session.execute(
            select(Score.tier, func.count(Score.lead_id))
            .join(Lead, Lead.id == Score.lead_id)
            .where(Lead.run_id == run_id)
            .group_by(Score.tier)
        )
    ).all()
    tier_counts = {tier: count for tier, count in tier_rows}

    # Email source distribution
    src_rows = (
        await session.execute(
            select(Email.source, func.count(Email.id))
            .join(Lead, Lead.id == Email.lead_id)
            .where(Lead.run_id == run_id)
            .group_by(Email.source)
        )
    ).all()
    src_counts = {src: count for src, count in src_rows}

    # API performance
    api_perf = await _api_perf_table(session, run_id)

    # Failed leads
    failed_leads = (
        await session.execute(
            select(Lead.id, Lead.email, Lead.error_message)
            .where(Lead.run_id == run_id, Lead.status == "failed")
            .limit(10)
        )
    ).all()

    md_lines: list[str] = []
    md_lines.append(f"# Run {run_id}")
    md_lines.append("")
    status_icon = {"success": "✅", "partial": "⚠️", "crashed": "❌", "running": "⏳"}.get(
        run.status, "?"
    )
    md_lines.append(
        f"**Status**: {status_icon} {run.status} "
        f"({run.success_count}/{run.lead_count} processed)"
    )
    md_lines.append("")
    md_lines.append(f"- Started: {_fmt_time(run.started_at)}")
    md_lines.append(f"- Finished: {_fmt_time(run.finished_at)}")
    md_lines.append("")
    md_lines.append("## Summary")
    md_lines.append("")
    md_lines.append(f"- Total leads: {run.lead_count}")
    md_lines.append(f"- Success: {run.success_count}")
    md_lines.append(f"- Failed: {run.failure_count}")
    if tier_counts:
        tier_str = " / ".join(
            f"{c} {t}" for t, c in sorted(tier_counts.items())
        )
        md_lines.append(f"- Tier distribution: {tier_str}")
    if src_counts:
        md_lines.append("- Email source:")
        for s, c in sorted(src_counts.items()):
            md_lines.append(f"  - `{s}`: {c}")
    md_lines.append("")
    md_lines.append("## API Performance")
    md_lines.append("")
    if api_perf:
        md_lines.append("| API | Calls | Avg ms | P95 ms | Failures |")
        md_lines.append("|---|---|---|---|---|")
        for row in api_perf:
            md_lines.append(
                f"| {row['api_name']} | {row['count']} | "
                f"{row['avg']} | {row['p95']} | {row['failures']} |"
            )
    else:
        md_lines.append("_No API calls recorded for this run._")
    md_lines.append("")
    if failed_leads:
        md_lines.append("## Failed Leads (top 10)")
        md_lines.append("")
        for lead_id, lead_email, err in failed_leads:
            md_lines.append(
                f"- `{lead_email}` — {(err or 'unknown error')[:120]}"
            )
        md_lines.append("")

    return "\n".join(md_lines)


async def _api_perf_table(
    session: AsyncSession, run_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Aggregate ApiLog rows into per-source perf metrics."""
    rows = (
        await session.execute(
            select(ApiLog.api_name, ApiLog.duration_ms, ApiLog.success)
            .where(ApiLog.run_id == run_id)
        )
    ).all()
    if not rows:
        return []

    grouped: dict[str, list[tuple[int, bool]]] = {}
    for api_name, dur, success in rows:
        grouped.setdefault(api_name, []).append((dur, success))

    out: list[dict[str, Any]] = []
    for api_name, samples in sorted(grouped.items()):
        durations = [d for d, _ in samples]
        failures = sum(1 for _, s in samples if not s)
        out.append(
            {
                "api_name": api_name,
                "count": len(samples),
                "avg": int(statistics.mean(durations)) if durations else 0,
                "p95": int(_percentile(durations, 95) or 0),
                "failures": failures,
            }
        )
    return out
