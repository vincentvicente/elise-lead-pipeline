import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronUp, Inbox as InboxIcon } from "lucide-react";
import { useLead, useLeads } from "@/api/hooks";
import { EmailEditor } from "@/components/EmailEditor";
import { PageHeader } from "@/components/PageHeader";
import { ProvenancePanel } from "@/components/ProvenancePanel";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { TierBadge } from "@/components/StatusBadge";
import { cn, relativeTime } from "@/lib/utils";

const HARDCODED_SDR = "sdr@elise.ai";

/** Inbox page — split view: pending lead list on left, focus on right.
 *
 * The Inbox shows processed leads that haven't been actioned yet (no
 * feedback row). After approve/reject, the next pending lead auto-selects
 * so the SDR can keep moving (PART_A v2 §8.2).
 */
export function Inbox() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("lead") ?? undefined;

  // List processed leads, ordered most recent first
  const { data: list, isLoading } = useLeads({
    status: "processed",
    pageSize: 50,
  });

  // Auto-select the first lead if none chosen
  useEffect(() => {
    if (!selectedId && list?.leads.length) {
      setSearchParams({ lead: list.leads[0].id }, { replace: true });
    }
  }, [list, selectedId, setSearchParams]);

  const detail = useLead(selectedId);

  // Sort by score descending (Hot first), then upload time
  const sortedLeads = useMemo(() => {
    if (!list) return [];
    return [...list.leads].sort((a, b) => {
      const sa = a.score_total ?? -1;
      const sb = b.score_total ?? -1;
      if (sa !== sb) return sb - sa;
      return (
        new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
      );
    });
  }, [list]);

  return (
    <div className="flex h-full">
      {/* Left: lead inbox */}
      <aside className="w-96 border-r border-slate-200 overflow-y-auto bg-white">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
          <InboxIcon className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-medium">Inbox</span>
          <span className="ml-auto text-xs text-slate-500">
            {list?.total ?? 0} processed
          </span>
        </div>

        {isLoading ? (
          <div className="p-4 text-sm text-slate-400">Loading...</div>
        ) : sortedLeads.length === 0 ? (
          <div className="p-4 text-sm text-slate-400">
            No processed leads yet — upload some and trigger a run.
          </div>
        ) : (
          <ul>
            {sortedLeads.map((lead) => (
              <li key={lead.id}>
                <button
                  onClick={() =>
                    setSearchParams({ lead: lead.id }, { replace: true })
                  }
                  className={cn(
                    "w-full text-left px-4 py-3 border-b border-slate-100 hover:bg-slate-50",
                    lead.id === selectedId && "bg-blue-50 border-l-2 border-l-blue-600"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="font-medium text-sm text-slate-900 truncate">
                      {lead.name}
                    </div>
                    <TierBadge tier={lead.score_tier} />
                  </div>
                  <div className="text-xs text-slate-500 truncate mt-0.5">
                    {lead.company}
                  </div>
                  <div className="flex justify-between text-xs text-slate-400 mt-1">
                    <span>
                      {lead.city}, {lead.state}
                    </span>
                    <span>{relativeTime(lead.processed_at)}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      {/* Right: focus pane */}
      <section className="flex-1 overflow-y-auto p-6">
        {!selectedId ? (
          <div className="text-slate-400 text-sm">
            Select a lead to review.
          </div>
        ) : detail.isLoading ? (
          <div className="text-slate-400 text-sm">Loading lead...</div>
        ) : detail.error || !detail.data ? (
          <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700">
            {(detail.error as Error)?.message ?? "Lead not found"}
          </div>
        ) : (
          <div className="max-w-3xl mx-auto">
            <PageHeader
              title={detail.data.name}
              subtitle={`${detail.data.company} · ${detail.data.email}`}
              actions={
                <button
                  onClick={() => navigate(`/leads/${detail.data!.id}`)}
                  className="btn-ghost text-xs"
                >
                  Open full detail →
                </button>
              }
            />

            {/* Insights */}
            {detail.data.insights.length > 0 && (
              <div className="card p-3 mb-4 bg-slate-50">
                <ul className="space-y-1 text-sm text-slate-700">
                  {detail.data.insights.slice(0, 4).map((b, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-slate-400">•</span>
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Score collapse */}
            {detail.data.score && (
              <details className="mb-4">
                <summary className="text-xs text-slate-500 cursor-pointer flex items-center gap-1">
                  <ChevronDown className="w-3 h-3" />
                  Score breakdown ({detail.data.score.total}/100,{" "}
                  {detail.data.score.tier})
                </summary>
                <div className="mt-2">
                  <ScoreBreakdown score={detail.data.score} />
                </div>
              </details>
            )}

            {/* Email editor */}
            {detail.data.email_draft && (
              <EmailEditor
                leadId={detail.data.id}
                email={detail.data.email_draft}
                sdrEmail={HARDCODED_SDR}
              />
            )}

            {/* Provenance collapse */}
            <details className="mt-4">
              <summary className="text-xs text-slate-500 cursor-pointer flex items-center gap-1">
                <ChevronUp className="w-3 h-3" />
                Source attribution ({detail.data.provenance.length} facts)
              </summary>
              <div className="mt-2">
                <ProvenancePanel facts={detail.data.provenance} />
              </div>
            </details>
          </div>
        )}
      </section>
    </div>
  );
}
