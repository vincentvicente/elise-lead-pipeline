import { cn } from "@/lib/utils";
import type { KpiCard as KpiCardData } from "@/api/types";

export function KPICard({ data }: { data: KpiCardData }) {
  const { label, value, unit, delta_pct } = data;
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <div className="text-3xl font-semibold text-slate-900">{value}</div>
        {unit && <div className="text-sm text-slate-500">{unit}</div>}
      </div>
      {delta_pct !== null && delta_pct !== undefined && (
        <div
          className={cn(
            "mt-1 text-xs",
            delta_pct >= 0 ? "text-emerald-600" : "text-rose-600"
          )}
        >
          {delta_pct >= 0 ? "↑" : "↓"} {Math.abs(delta_pct).toFixed(1)}% vs prev
        </div>
      )}
    </div>
  );
}
