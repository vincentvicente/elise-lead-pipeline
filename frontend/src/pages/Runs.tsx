import { useState } from "react";
import { Link } from "react-router-dom";
import { useRuns, useTriggerRun } from "@/api/hooks";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate, relativeTime } from "@/lib/utils";
import { Loader2, Play } from "lucide-react";

export function Runs() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useRuns(page, 20);
  const trigger = useTriggerRun();

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <PageHeader
        title="Run history"
        subtitle="Cron and on-demand pipeline executions"
        actions={
          <button
            onClick={() => trigger.mutate()}
            disabled={trigger.isPending}
            className="btn-primary"
          >
            {trigger.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            Trigger run
          </button>
        }
      />

      {trigger.isSuccess && (
        <div className="card p-3 mb-4 bg-emerald-50 border-emerald-200 text-emerald-700 text-sm">
          Pipeline scheduled. Run id:{" "}
          <Link
            to={`/runs/${trigger.data.run_id}`}
            className="font-mono underline"
          >
            {trigger.data.run_id.slice(0, 8)}…
          </Link>
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Started</th>
              <th className="px-4 py-2 font-medium">Duration</th>
              <th className="px-4 py-2 font-medium">Leads</th>
              <th className="px-4 py-2 font-medium text-right"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr>
                <td colSpan={5} className="text-center text-slate-400 py-8">
                  Loading...
                </td>
              </tr>
            )}
            {data?.runs.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center text-slate-400 py-8">
                  No runs yet — click "Trigger run" to kick one off.
                </td>
              </tr>
            )}
            {data?.runs.map((r) => {
              const dur =
                r.finished_at && r.started_at
                  ? Math.round(
                      (new Date(r.finished_at).getTime() -
                        new Date(r.started_at).getTime()) /
                        1000
                    )
                  : null;
              return (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-2.5 text-slate-700">
                    <div>{formatDate(r.started_at)}</div>
                    <div className="text-xs text-slate-500">
                      {relativeTime(r.started_at)}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-slate-700">
                    {dur !== null ? `${dur}s` : r.status === "running" ? "..." : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-slate-700">
                    {r.success_count}/{r.lead_count}
                    {r.failure_count > 0 && (
                      <span className="text-rose-600 ml-1">
                        ({r.failure_count} failed)
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link
                      to={`/runs/${r.id}`}
                      className="text-blue-700 hover:underline text-sm"
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-between mt-4 text-sm">
          <div className="text-slate-500">
            Showing {(page - 1) * data.page_size + 1}–
            {Math.min(page * data.page_size, data.total)} of {data.total}
          </div>
          <div className="flex gap-2">
            <button
              className="btn-secondary"
              disabled={page === 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Prev
            </button>
            <button
              className="btn-secondary"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
