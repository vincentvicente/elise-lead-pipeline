import type { ProvenanceFact } from "@/api/types";
import { relativeTime } from "@/lib/utils";

export function ProvenancePanel({ facts }: { facts: ProvenanceFact[] }) {
  if (facts.length === 0) {
    return (
      <div className="card p-4 text-sm text-slate-400">
        No provenance recorded for this lead yet.
      </div>
    );
  }

  // Group by source for compact display
  const grouped = facts.reduce<Record<string, ProvenanceFact[]>>((acc, f) => {
    (acc[f.source] ??= []).push(f);
    return acc;
  }, {});

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium text-slate-900">
          Source Attribution ({facts.length} facts)
        </h3>
        <div className="text-xs text-slate-500">
          Confidence ≥ 0.85 = citable; below = topic-only
        </div>
      </div>
      <div className="space-y-3">
        {Object.entries(grouped).map(([source, items]) => (
          <div key={source}>
            <div className="text-xs font-mono text-slate-500 mb-1">
              {source}
            </div>
            <ul className="space-y-1 ml-3">
              {items.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <span
                    className={
                      f.confidence >= 0.85
                        ? "px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-mono"
                        : "px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-mono"
                    }
                  >
                    {f.confidence.toFixed(2)}
                  </span>
                  <div className="flex-1">
                    <span className="font-medium text-slate-700">
                      {f.fact_key}:
                    </span>{" "}
                    <span className="text-slate-600">
                      {formatValue(f.fact_value)}
                    </span>
                    <span className="text-slate-400 ml-2">
                      {relativeTime(f.fetched_at)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}
