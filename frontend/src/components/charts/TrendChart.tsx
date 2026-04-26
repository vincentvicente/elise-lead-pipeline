import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "@/api/types";

export function TrendChart({ data }: { data: TrendPoint[] }) {
  const formatted = data.map((p) => ({
    ...p,
    label: new Date(p.day).toLocaleDateString("en-US", {
      weekday: "short",
      day: "numeric",
    }),
  }));

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-slate-900">7-day Trend</h3>
        <div className="text-xs text-slate-500">Leads processed per day</div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={formatted} margin={{ top: 5, right: 16, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 12, fill: "#64748b" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "#64748b" }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                fontSize: 12,
                background: "white",
                border: "1px solid #e2e8f0",
                borderRadius: 6,
              }}
            />
            <Line
              type="monotone"
              dataKey="leads_processed"
              stroke="#1e40af"
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
