import { cn } from "@/lib/utils";

export function TierBadge({ tier }: { tier: string | null | undefined }) {
  if (!tier) return <span className="text-slate-400">—</span>;
  const cls =
    tier === "Hot"
      ? "badge-hot"
      : tier === "Warm"
        ? "badge-warm"
        : "badge-cold";
  return <span className={cls}>{tier}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const palette: Record<string, string> = {
    pending: "bg-slate-100 text-slate-600",
    processing: "bg-blue-100 text-blue-700",
    processed: "bg-emerald-100 text-emerald-700",
    failed: "bg-rose-100 text-rose-700",
    success: "bg-emerald-100 text-emerald-700",
    partial: "bg-amber-100 text-amber-700",
    crashed: "bg-rose-100 text-rose-700",
    running: "bg-blue-100 text-blue-700",
    queued: "bg-slate-100 text-slate-600",
  };
  return (
    <span
      className={cn(
        "badge",
        palette[status] ?? "bg-slate-100 text-slate-600"
      )}
    >
      {status}
    </span>
  );
}
