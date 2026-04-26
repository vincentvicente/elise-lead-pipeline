import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind class merger — handles conflicts (e.g. `p-2 p-4` → `p-4`). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** "12 minutes ago" / "3 days ago" — minimal humanizer. */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (isNaN(ts)) return iso;
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function tierClass(tier: string | null | undefined): string {
  switch (tier) {
    case "Hot":
      return "badge-hot";
    case "Warm":
      return "badge-warm";
    case "Cold":
      return "badge-cold";
    default:
      return "badge-cold";
  }
}

export function tierColor(tier: string | null | undefined): string {
  switch (tier) {
    case "Hot":
      return "#ef4444";
    case "Warm":
      return "#f59e0b";
    case "Cold":
      return "#64748b";
    default:
      return "#94a3b8";
  }
}
