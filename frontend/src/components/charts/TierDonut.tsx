import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { TierDistribution } from "@/api/types";

const TIER_COLORS: Record<string, string> = {
  Hot: "#ef4444",
  Warm: "#f59e0b",
  Cold: "#64748b",
};

export function TierDonut({ data }: { data: TierDistribution }) {
  const items = [
    { name: "Hot", value: data.hot },
    { name: "Warm", value: data.warm },
    { name: "Cold", value: data.cold },
  ];
  const total = items.reduce((s, i) => s + i.value, 0);

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-slate-900">Tier Distribution</h3>
        <div className="text-xs text-slate-500">Today</div>
      </div>
      {total === 0 ? (
        <div className="h-64 flex items-center justify-center text-slate-400 text-sm">
          No leads scored today
        </div>
      ) : (
        <div className="h-64 grid grid-cols-2 items-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={items}
                dataKey="value"
                nameKey="name"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
              >
                {items.map((it) => (
                  <Cell key={it.name} fill={TIER_COLORS[it.name]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-2 text-sm">
            {items.map((it) => (
              <div key={it.name} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ background: TIER_COLORS[it.name] }}
                  />
                  <span className="text-slate-700">{it.name}</span>
                </div>
                <div className="font-medium text-slate-900">{it.value}</div>
              </div>
            ))}
            <div className="border-t border-slate-200 pt-2 flex justify-between text-xs text-slate-500">
              <span>Total</span>
              <span>{total}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
