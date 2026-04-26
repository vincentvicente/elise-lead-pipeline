"""Metrics schemas — power the dashboard Overview page charts."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class KpiCard(BaseModel):
    """Single KPI tile for the Overview page."""

    label: str
    value: float | int | str
    unit: str | None = None  # e.g. "%", "leads", "min"
    delta_pct: float | None = None  # vs previous window (None when not computable)


class TrendPoint(BaseModel):
    """One point in a time-series chart (e.g. 7-day trend)."""

    day: date
    leads_processed: int
    approval_rate: float | None = None  # 0.0–1.0
    hot_pct: float | None = None        # 0.0–1.0


class TierDistribution(BaseModel):
    hot: int
    warm: int
    cold: int


class RecentRunSummary(BaseModel):
    id: str
    started_at: datetime
    status: str
    success_count: int
    failure_count: int
    lead_count: int


class OverviewResponse(BaseModel):
    """GET /api/v1/metrics/overview payload."""

    kpis: list[KpiCard]
    trend: list[TrendPoint]
    tier_distribution: TierDistribution
    recent_runs: list[RecentRunSummary]


class ApiPerformancePoint(BaseModel):
    """Per-API perf metrics over a window (used by /metrics/api-performance)."""

    api_name: str
    total_calls: int
    success_count: int
    failure_count: int
    avg_ms: int
    p95_ms: int
    failure_rate: float  # 0.0–1.0
