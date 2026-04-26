import { Link, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useLeads, useRun } from "@/api/hooks";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge, TierBadge } from "@/components/StatusBadge";
import { formatDate } from "@/lib/utils";

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const { data: run, isLoading, error } = useRun(runId);
  const { data: leads } = useLeads({ runId, pageSize: 100 });

  if (isLoading) {
    return <div className="p-6 text-slate-400">Loading...</div>;
  }
  if (error || !run) {
    return (
      <div className="p-6 max-w-[1400px] mx-auto">
        <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700">
          {error ? (error as Error).message : "Run not found"}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <Link
        to="/runs"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-3"
      >
        <ChevronLeft className="w-4 h-4" />
        Back to runs
      </Link>

      <PageHeader
        title={`Run ${runId?.slice(0, 8)}…`}
        subtitle={`Started ${formatDate(run.started_at)} · Finished ${
          run.finished_at ? formatDate(run.finished_at) : "—"
        }`}
        actions={<StatusBadge status={run.status} />}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Stat label="Total leads" value={run.lead_count} />
        <Stat label="Successful" value={run.success_count} accent="emerald" />
        <Stat label="Failed" value={run.failure_count} accent="rose" />
      </div>

      {/* Markdown report */}
      <div className="card p-6 mb-6">
        <h3 className="font-medium text-slate-900 mb-4">Run report</h3>
        {run.report_md ? (
          <div className="prose prose-sm max-w-none prose-slate prose-table:text-sm prose-th:bg-slate-50 prose-th:px-3 prose-td:px-3">
            <ReactMarkdown>{run.report_md}</ReactMarkdown>
          </div>
        ) : (
          <div className="text-slate-400 text-sm">
            Report not yet generated (run still in progress?)
          </div>
        )}
      </div>

      {/* Leads in this run */}
      {leads && leads.leads.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 font-medium">
            Leads in this run ({leads.total})
          </div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 text-left">Name</th>
                <th className="px-4 py-2 text-left">Company</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-left">Score</th>
                <th className="px-4 py-2 text-left">Tier</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {leads.leads.map((l) => (
                <tr key={l.id}>
                  <td className="px-4 py-2">
                    <Link
                      to={`/leads/${l.id}`}
                      className="text-blue-700 hover:underline"
                    >
                      {l.name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-700">{l.company}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={l.status} />
                  </td>
                  <td className="px-4 py-2 text-slate-700">
                    {l.score_total ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <TierBadge tier={l.score_tier} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent = "slate",
}: {
  label: string;
  value: number | string;
  accent?: "slate" | "emerald" | "rose";
}) {
  const colorClass =
    accent === "emerald"
      ? "text-emerald-700"
      : accent === "rose"
        ? "text-rose-700"
        : "text-slate-900";
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={"text-3xl font-semibold mt-1 " + colorClass}>{value}</div>
    </div>
  );
}
