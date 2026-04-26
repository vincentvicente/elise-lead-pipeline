import { useState } from "react";
import { Link } from "react-router-dom";
import { useLeads } from "@/api/hooks";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge, TierBadge } from "@/components/StatusBadge";
import { relativeTime } from "@/lib/utils";

export function Leads() {
  const [tier, setTier] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useLeads({
    page,
    pageSize: 50,
    tier: tier || undefined,
    status: status || undefined,
  });

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <PageHeader
        title="All Leads"
        subtitle={
          data ? `${data.total} total leads` : "Browse and filter inbound leads"
        }
      />

      {/* Filters */}
      <div className="card p-3 mb-4 flex gap-3 items-center text-sm">
        <select
          value={tier}
          onChange={(e) => {
            setTier(e.target.value);
            setPage(1);
          }}
          className="border border-slate-300 rounded-md px-2 py-1.5"
        >
          <option value="">All tiers</option>
          <option value="Hot">Hot</option>
          <option value="Warm">Warm</option>
          <option value="Cold">Cold</option>
        </select>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="border border-slate-300 rounded-md px-2 py-1.5"
        >
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="processing">Processing</option>
          <option value="processed">Processed</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Location</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Score</th>
              <th className="px-4 py-2 font-medium">Tier</th>
              <th className="px-4 py-2 font-medium">Uploaded</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr>
                <td colSpan={7} className="text-center text-slate-400 py-8">
                  Loading...
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={7} className="text-center text-rose-600 py-8">
                  {(error as Error).message}
                </td>
              </tr>
            )}
            {data?.leads.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center text-slate-400 py-8">
                  No leads match these filters.
                </td>
              </tr>
            )}
            {data?.leads.map((lead) => (
              <tr key={lead.id} className="hover:bg-slate-50">
                <td className="px-4 py-2.5">
                  <Link
                    to={`/leads/${lead.id}`}
                    className="text-slate-900 hover:text-blue-700 font-medium"
                  >
                    {lead.name}
                  </Link>
                  <div className="text-xs text-slate-500">{lead.email}</div>
                </td>
                <td className="px-4 py-2.5 text-slate-700">{lead.company}</td>
                <td className="px-4 py-2.5 text-slate-700">
                  {lead.city}, {lead.state}
                </td>
                <td className="px-4 py-2.5">
                  <StatusBadge status={lead.status} />
                </td>
                <td className="px-4 py-2.5 text-slate-700">
                  {lead.score_total ?? "—"}
                </td>
                <td className="px-4 py-2.5">
                  <TierBadge tier={lead.score_tier} />
                </td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">
                  {relativeTime(lead.uploaded_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
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
