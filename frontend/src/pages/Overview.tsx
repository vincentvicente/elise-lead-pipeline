import { Link } from "react-router-dom";
import { useOverview } from "@/api/hooks";
import { KPICard } from "@/components/KPICard";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { TodayProgress } from "@/components/TodayProgress";
import { TrendChart } from "@/components/charts/TrendChart";
import { TierDonut } from "@/components/charts/TierDonut";
import { relativeTime } from "@/lib/utils";

export function Overview() {
  const { data, isLoading, error } = useOverview();

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <PageHeader
        title="Overview"
        subtitle="Pipeline health, tier distribution, and recent runs"
      />

      {error && (
        <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700 mb-6">
          Failed to load metrics: {(error as Error).message}
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {isLoading
          ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="card p-4 animate-pulse h-[100px]" />
            ))
          : data?.kpis.map((kpi) => <KPICard key={kpi.label} data={kpi} />)}
      </div>

      {/* Today's progress — Sheet-style scannable status row */}
      {data && (
        <TodayProgress
          tierToday={data.tier_distribution}
          recentRuns={data.recent_runs}
        />
      )}

      {/* Trend + Tier donut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="lg:col-span-2">
          {data && <TrendChart data={data.trend} />}
        </div>
        <div>{data && <TierDonut data={data.tier_distribution} />}</div>
      </div>

      {/* Recent runs */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-medium text-slate-900">Recent runs</h3>
          <Link to="/runs" className="text-sm text-blue-700 hover:underline">
            View all →
          </Link>
        </div>
        {(!data || data.recent_runs.length === 0) && (
          <div className="text-sm text-slate-500 py-4">No runs yet.</div>
        )}
        <div className="divide-y divide-slate-100">
          {data?.recent_runs.map((r) => (
            <Link
              key={r.id}
              to={`/runs/${r.id}`}
              className="flex items-center justify-between py-2 hover:bg-slate-50 -mx-2 px-2 rounded"
            >
              <div className="flex items-center gap-3">
                <StatusBadge status={r.status} />
                <span className="text-sm text-slate-700">
                  {r.success_count}/{r.lead_count} processed
                  {r.failure_count > 0 && (
                    <span className="text-rose-600 ml-1">
                      · {r.failure_count} failed
                    </span>
                  )}
                </span>
              </div>
              <span className="text-xs text-slate-500">
                {relativeTime(r.started_at)}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
