import type { ScoreOut } from "@/api/types";
import { TierBadge } from "@/components/StatusBadge";

const DIM_LABELS: Record<string, { label: string; max: number }> = {
  company_scale: { label: "Company Scale", max: 25 },
  buy_intent: { label: "Buy Intent", max: 20 },
  vertical_fit: { label: "Vertical Fit", max: 10 },
  market_fit: { label: "Market Fit", max: 15 },
  property_fit: { label: "Property Fit", max: 10 },
  market_dynamics: { label: "Market Dynamics", max: 5 },
  contact_fit: { label: "Contact Fit", max: 15 },
};

export function ScoreBreakdown({ score }: { score: ScoreOut }) {
  return (
    <div className="card p-4">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Lead score
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-semibold">{score.total}</span>
            <span className="text-slate-400">/ 100</span>
          </div>
        </div>
        <TierBadge tier={score.tier} />
      </div>

      <div className="space-y-2.5">
        {Object.entries(DIM_LABELS).map(([key, meta]) => {
          const points = score.breakdown[key] ?? 0;
          const pct = meta.max > 0 ? (points / meta.max) * 100 : 0;
          return (
            <div key={key}>
              <div className="flex justify-between text-xs text-slate-600 mb-0.5">
                <span>{meta.label}</span>
                <span className="font-medium">
                  {points} / {meta.max}
                </span>
              </div>
              <div className="h-1.5 bg-slate-100 rounded">
                <div
                  className="h-1.5 bg-blue-600 rounded transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {score.reasons.length > 0 && (
        <details className="mt-4">
          <summary className="text-xs text-slate-500 cursor-pointer">
            Why this score? ({score.reasons.length} signals)
          </summary>
          <ul className="mt-2 space-y-1 text-xs text-slate-600 max-h-48 overflow-y-auto">
            {score.reasons.map((r, i) => (
              <li key={i} className="leading-relaxed">
                {r}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
