import { Link, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { useLead } from "@/api/hooks";
import { EmailEditor } from "@/components/EmailEditor";
import { PageHeader } from "@/components/PageHeader";
import { ProvenancePanel } from "@/components/ProvenancePanel";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { StatusBadge, TierBadge } from "@/components/StatusBadge";
import { formatDate, relativeTime } from "@/lib/utils";

// Hardcoded SDR identity for MVP — production would come from auth.
const HARDCODED_SDR = "sdr@elise.ai";

export function LeadDetail() {
  const { leadId } = useParams<{ leadId: string }>();
  const { data, isLoading, error } = useLead(leadId);

  if (isLoading) {
    return (
      <div className="p-6 text-slate-400 max-w-[1400px] mx-auto">Loading…</div>
    );
  }
  if (error || !data) {
    return (
      <div className="p-6 max-w-[1400px] mx-auto">
        <div className="card p-4 bg-rose-50 border-rose-200 text-rose-700">
          {error ? (error as Error).message : "Lead not found"}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <Link
        to="/leads"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-3"
      >
        <ChevronLeft className="w-4 h-4" />
        Back to leads
      </Link>

      <PageHeader
        title={data.name}
        subtitle={`${data.company} · ${data.email}`}
        actions={
          <>
            <StatusBadge status={data.status} />
            {data.score && <TierBadge tier={data.score.tier} />}
          </>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left column — score, lead facts, insights */}
        <div className="space-y-4">
          {/* Insights */}
          <div className="card p-4">
            <h3 className="font-medium text-slate-900 mb-3">Insights</h3>
            {data.insights.length === 0 ? (
              <div className="text-sm text-slate-400">
                Lead not processed yet.
              </div>
            ) : (
              <ul className="space-y-2 text-sm text-slate-700">
                {data.insights.map((bullet, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-slate-400">•</span>
                    <span className="leading-relaxed">{bullet}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Score breakdown */}
          {data.score && <ScoreBreakdown score={data.score} />}

          {/* Lead fields */}
          <div className="card p-4 text-sm">
            <h3 className="font-medium text-slate-900 mb-3">Lead</h3>
            <dl className="space-y-1.5">
              <Row k="Property" v={data.property_address} />
              <Row k="City" v={`${data.city}, ${data.state}, ${data.country}`} />
              <Row k="Status" v={data.status} />
              <Row k="Uploaded" v={formatDate(data.uploaded_at)} />
              <Row
                k="Processed"
                v={data.processed_at ? formatDate(data.processed_at) : "—"}
              />
              {data.run_id && (
                <Row
                  k="Run"
                  v={
                    <Link
                      to={`/runs/${data.run_id}`}
                      className="text-blue-700 hover:underline font-mono text-xs"
                    >
                      {data.run_id.slice(0, 8)}…
                    </Link>
                  }
                />
              )}
              {data.error_message && (
                <Row k="Error" v={data.error_message} />
              )}
            </dl>
          </div>
        </div>

        {/* Center — email editor */}
        <div className="lg:col-span-2 space-y-4">
          {data.email_draft ? (
            <EmailEditor
              leadId={data.id}
              email={data.email_draft}
              sdrEmail={HARDCODED_SDR}
            />
          ) : (
            <div className="card p-4 text-slate-500 text-sm">
              No email draft yet — process this lead to generate one.
            </div>
          )}

          {/* Feedback history */}
          {data.feedback.length > 0 && (
            <div className="card p-4">
              <h3 className="font-medium text-slate-900 mb-3">
                Feedback history ({data.feedback.length})
              </h3>
              <ul className="divide-y divide-slate-100">
                {data.feedback.map((fb) => (
                  <li key={fb.id} className="py-2 text-sm">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className={
                            fb.action === "approved"
                              ? "badge bg-emerald-100 text-emerald-700"
                              : fb.action === "edited"
                                ? "badge bg-blue-100 text-blue-700"
                                : "badge bg-rose-100 text-rose-700"
                          }
                        >
                          {fb.action}
                        </span>
                        <span className="text-slate-700">
                          {fb.sdr_email}
                        </span>
                        <span className="text-xs text-slate-500">
                          ({fb.review_seconds}s review)
                        </span>
                      </div>
                      <span className="text-xs text-slate-500">
                        {relativeTime(fb.created_at)}
                      </span>
                    </div>
                    {fb.rejection_reason && (
                      <div className="text-xs text-slate-500 mt-1 pl-2">
                        “{fb.rejection_reason}”
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Provenance */}
          <ProvenancePanel facts={data.provenance} />
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="text-slate-500 w-24 flex-shrink-0">{k}</dt>
      <dd className="text-slate-700">{v}</dd>
    </div>
  );
}
