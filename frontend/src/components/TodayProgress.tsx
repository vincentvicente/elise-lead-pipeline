import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, Clock, AlertTriangle } from "lucide-react";
import { useLeads } from "@/api/hooks";
import type { TierDistribution, RecentRunSummary } from "@/api/types";

interface Props {
  tierToday: TierDistribution;
  recentRuns: RecentRunSummary[];
}

/** Compact "today's progress" card — mirrors the Sheet-style "X of Y processed"
 * scan-able status surface. Sits between the KPI row and the chart row.
 */
export function TodayProgress({ tierToday, recentRuns }: Props) {
  const totalToday = tierToday.hot + tierToday.warm + tierToday.cold;
  const lastRun = recentRuns[0];

  // Pending count
  const pending = useLeads({ status: "pending", pageSize: 1 });
  const pendingCount = pending.data?.total ?? 0;

  return (
    <div className="card p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium text-slate-900">Today's pipeline</h3>
        {lastRun && (
          <Link
            to={`/runs/${lastRun.id}`}
            className="text-xs text-slate-500 hover:text-blue-700"
          >
            Last run: {new Date(lastRun.started_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}{" "}
            · {lastRun.status} →
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Processed today */}
        <Tile
          icon={<CheckCircle2 className="w-4 h-4 text-emerald-600" />}
          label="Processed today"
          value={totalToday}
          breakdown={
            totalToday > 0 ? (
              <span className="text-xs text-slate-500">
                <span className="text-rose-600 font-medium">
                  {tierToday.hot} Hot
                </span>{" "}
                ·{" "}
                <span className="text-amber-600 font-medium">
                  {tierToday.warm} Warm
                </span>{" "}
                ·{" "}
                <span className="text-slate-500 font-medium">
                  {tierToday.cold} Cold
                </span>
              </span>
            ) : null
          }
        />

        {/* Pending */}
        <Tile
          icon={<Clock className="w-4 h-4 text-blue-600" />}
          label="Pending review"
          value={pendingCount}
          breakdown={
            pendingCount > 0 ? (
              <Link
                to="/leads?status=pending"
                className="text-xs text-blue-700 hover:underline inline-flex items-center gap-0.5"
              >
                view <ArrowRight className="w-3 h-3" />
              </Link>
            ) : (
              <span className="text-xs text-slate-400">queue empty</span>
            )
          }
        />

        {/* Last run health */}
        <Tile
          icon={
            lastRun && lastRun.failure_count > 0 ? (
              <AlertTriangle className="w-4 h-4 text-amber-600" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            )
          }
          label="Last run health"
          value={
            lastRun
              ? `${lastRun.success_count}/${lastRun.lead_count}`
              : "—"
          }
          breakdown={
            lastRun ? (
              <span className="text-xs text-slate-500">
                {lastRun.failure_count > 0
                  ? `${lastRun.failure_count} failed → see report`
                  : "all clean"}
              </span>
            ) : null
          }
        />
      </div>
    </div>
  );
}

function Tile({
  icon,
  label,
  value,
  breakdown,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  breakdown: React.ReactNode;
}) {
  return (
    <div className="bg-slate-50 rounded-md px-3 py-2 border border-slate-100">
      <div className="flex items-center gap-1.5 text-xs text-slate-600">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-semibold text-slate-900 mt-0.5">{value}</div>
      <div className="mt-0.5">{breakdown}</div>
    </div>
  );
}
