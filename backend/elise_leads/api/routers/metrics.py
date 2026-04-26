"""/api/v1/metrics — dashboard Overview + API performance charts."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from elise_leads.api.deps import get_session
from elise_leads.api.schemas.metrics import (
    ApiPerformancePoint,
    KpiCard,
    OverviewResponse,
    RecentRunSummary,
    TierDistribution,
    TrendPoint,
)
from elise_leads.models import (
    ApiLog,
    Email,
    Feedback,
    Lead,
    Run,
    Score,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/overview", response_model=OverviewResponse, summary="Overview KPIs + trend")
async def overview(
    session: AsyncSession = Depends(get_session),
) -> OverviewResponse:
    """Top-of-dashboard KPIs + 7-day trend + tier distribution + recent runs.

    All queries scoped to the last 7 days (or "today" for the KPI deltas).
    """
    now = _utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)

    # --- KPI: leads processed today ---
    today_processed = (
        await session.execute(
            select(func.count(Lead.id)).where(
                Lead.status == "processed",
                Lead.processed_at >= today_start,
            )
        )
    ).scalar_one()

    # --- KPI: hot tier % over last 7 days ---
    tier_rows = (
        await session.execute(
            select(Score.tier, func.count(Score.lead_id))
            .join(Lead, Lead.id == Score.lead_id)
            .where(Lead.processed_at >= week_start)
            .group_by(Score.tier)
        )
    ).all()
    tiers = {t: c for t, c in tier_rows}
    total_scored = sum(tiers.values())
    hot_pct = (tiers.get("Hot", 0) / total_scored) if total_scored else 0.0

    # --- KPI: approval rate over last 7 days ---
    fb_rows = (
        await session.execute(
            select(Feedback.action, func.count(Feedback.id)).where(
                Feedback.created_at >= week_start
            ).group_by(Feedback.action)
        )
    ).all()
    fb_counts = {a: c for a, c in fb_rows}
    fb_total = sum(fb_counts.values())
    approval_rate = (fb_counts.get("approved", 0) / fb_total) if fb_total else 0.0

    # --- KPI: avg review_seconds (verification burden) ---
    avg_review_secs = (
        await session.execute(
            select(func.avg(Feedback.review_seconds)).where(
                Feedback.created_at >= week_start
            )
        )
    ).scalar_one()

    kpis = [
        KpiCard(label="Processed today", value=today_processed, unit="leads"),
        KpiCard(label="Hot tier %", value=round(hot_pct * 100, 1), unit="%"),
        KpiCard(
            label="Approval rate",
            value=round(approval_rate * 100, 1),
            unit="%",
        ),
        KpiCard(
            label="Avg review time",
            value=round((avg_review_secs or 0) / 60.0, 1),
            unit="min",
        ),
    ]

    # --- 7-day trend ---
    # Aggregate processed counts + feedback approval rate per day
    trend_rows = (
        await session.execute(
            select(
                func.date(Lead.processed_at).label("d"),
                func.count(Lead.id),
            )
            .where(Lead.processed_at >= week_start)
            .group_by("d")
            .order_by("d")
        )
    ).all()
    trend_map: dict[str, dict] = {}
    for d, c in trend_rows:
        trend_map[str(d)] = {"leads_processed": c}

    trend = []
    for offset in range(7):
        day = (week_start + timedelta(days=offset)).date()
        key = day.isoformat()
        item = trend_map.get(key, {"leads_processed": 0})
        trend.append(
            TrendPoint(
                day=day,
                leads_processed=item["leads_processed"],
                approval_rate=None,  # per-day approval is noisy; show window-level KPI instead
                hot_pct=None,
            )
        )

    # --- Tier distribution (today) ---
    tier_today_rows = (
        await session.execute(
            select(Score.tier, func.count(Score.lead_id))
            .join(Lead, Lead.id == Score.lead_id)
            .where(Lead.processed_at >= today_start)
            .group_by(Score.tier)
        )
    ).all()
    tt = {t: c for t, c in tier_today_rows}
    tier_dist = TierDistribution(
        hot=tt.get("Hot", 0), warm=tt.get("Warm", 0), cold=tt.get("Cold", 0)
    )

    # --- Recent runs (last 5) ---
    recent_runs = (
        await session.execute(
            select(Run).order_by(desc(Run.started_at)).limit(5)
        )
    ).scalars().all()

    return OverviewResponse(
        kpis=kpis,
        trend=trend,
        tier_distribution=tier_dist,
        recent_runs=[
            RecentRunSummary(
                id=str(r.id),
                started_at=r.started_at,
                status=r.status,
                success_count=r.success_count,
                failure_count=r.failure_count,
                lead_count=r.lead_count,
            )
            for r in recent_runs
        ],
    )


@router.get(
    "/api-performance",
    response_model=list[ApiPerformancePoint],
    summary="Per-API performance over the last N days",
)
async def api_performance(
    days: int = Query(30, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
) -> list[ApiPerformancePoint]:
    """Aggregates ApiLog rows into per-source perf metrics."""
    cutoff = _utcnow() - timedelta(days=days)

    rows = (
        await session.execute(
            select(ApiLog.api_name, ApiLog.duration_ms, ApiLog.success).where(
                ApiLog.started_at >= cutoff
            )
        )
    ).all()

    grouped: dict[str, list[tuple[int, bool]]] = {}
    for api_name, dur, success in rows:
        grouped.setdefault(api_name, []).append((dur, bool(success)))

    out: list[ApiPerformancePoint] = []
    for api_name, samples in sorted(grouped.items()):
        durations = [d for d, _ in samples]
        success = sum(1 for _, s in samples if s)
        failure = len(samples) - success
        sorted_d = sorted(durations)
        p95_idx = max(0, min(len(sorted_d) - 1, int(round(0.95 * (len(sorted_d) - 1)))))
        p95 = sorted_d[p95_idx] if sorted_d else 0
        out.append(
            ApiPerformancePoint(
                api_name=api_name,
                total_calls=len(samples),
                success_count=success,
                failure_count=failure,
                avg_ms=int(statistics.mean(durations)) if durations else 0,
                p95_ms=int(p95),
                failure_rate=(failure / len(samples)) if samples else 0.0,
            )
        )
    return out
