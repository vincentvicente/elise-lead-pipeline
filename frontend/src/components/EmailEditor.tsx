import { useEffect, useRef, useState } from "react";
import ReactDiffViewer from "react-diff-viewer-continued";
import { Check, X, Pencil, FileDiff, Loader2 } from "lucide-react";
import type { EmailOut, FeedbackCreate } from "@/api/types";
import { useSubmitFeedback } from "@/api/hooks";

interface Props {
  leadId: string;
  email: EmailOut;
  sdrEmail: string; // hardcoded for MVP — would come from auth in production
}

export function EmailEditor({ leadId, email, sdrEmail }: Props) {
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const [showDiff, setShowDiff] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  // Verification-burden timer — measures how long the SDR spent reviewing
  const openedAt = useRef<number>(Date.now());
  useEffect(() => {
    openedAt.current = Date.now();
  }, [email.id]);

  const submit = useSubmitFeedback(leadId);

  const isEdited = subject !== email.subject || body !== email.body;

  const submitFeedback = (payload: Omit<FeedbackCreate, "review_seconds" | "sdr_email">) => {
    const review_seconds = Math.floor((Date.now() - openedAt.current) / 1000);
    submit.mutate({
      ...payload,
      sdr_email: sdrEmail,
      review_seconds,
    });
  };

  const handleApprove = () => {
    if (isEdited) {
      submitFeedback({
        action: "edited",
        final_subject: subject,
        final_body: body,
      });
    } else {
      submitFeedback({ action: "approved" });
    }
  };

  const handleReject = () => {
    if (!rejectReason.trim()) return;
    submitFeedback({ action: "rejected", rejection_reason: rejectReason });
    setShowRejectModal(false);
  };

  const hallucinationOk = email.hallucination_check?.passed ?? true;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium text-slate-900">Email draft</h3>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="font-mono">{email.source}</span>
          {email.proof_point_used && (
            <>
              <span>·</span>
              <span>proof: {email.proof_point_used}</span>
            </>
          )}
        </div>
      </div>

      {/* Hallucination check banner */}
      <div
        className={
          "mb-3 px-3 py-2 rounded-md text-xs flex items-center gap-2 " +
          (hallucinationOk
            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
            : "bg-amber-50 text-amber-700 border border-amber-200")
        }
      >
        {hallucinationOk ? (
          <>
            <Check className="w-3.5 h-3.5" />
            Hallucination check passed
            {(email.hallucination_check?.warning_count ?? 0) > 0 && (
              <span className="ml-1">
                · {email.hallucination_check?.warning_count} warning(s)
              </span>
            )}
          </>
        ) : (
          <>
            <X className="w-3.5 h-3.5" />
            {email.hallucination_check?.severe_count ?? 0} severe issue(s) —
            review carefully
          </>
        )}
      </div>

      {/* Generation trail — surfaces the LLM fallback chain when applicable */}
      {email.warnings.length > 0 && (
        <div className="mb-3 px-3 py-2 rounded-md text-xs bg-amber-50 border border-amber-200 text-amber-800">
          <div className="font-medium mb-1">
            ⚠ Generation trail ({email.warnings.length})
          </div>
          <ul className="list-disc ml-4 space-y-0.5 font-mono text-[11px]">
            {email.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Subject */}
      <div className="mb-3">
        <label className="text-xs font-medium text-slate-600 block mb-1">
          Subject
        </label>
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
        />
      </div>

      {/* Body */}
      <div className="mb-4">
        <label className="text-xs font-medium text-slate-600 block mb-1">
          Body
        </label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={12}
          className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-200"
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={handleApprove}
          disabled={submit.isPending}
          className="btn-success"
        >
          {submit.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : isEdited ? (
            <Pencil className="w-4 h-4" />
          ) : (
            <Check className="w-4 h-4" />
          )}
          {isEdited ? "Save & Approve" : "Approve"}
        </button>

        {isEdited && (
          <button
            onClick={() => setShowDiff(true)}
            className="btn-secondary"
          >
            <FileDiff className="w-4 h-4" />
            View Changes
          </button>
        )}

        <button
          onClick={() => setShowRejectModal(true)}
          className="btn-danger ml-auto"
        >
          <X className="w-4 h-4" />
          Reject
        </button>
      </div>

      {submit.error && (
        <div className="mt-3 text-sm text-rose-600">
          {(submit.error as Error).message}
        </div>
      )}
      {submit.isSuccess && (
        <div className="mt-3 text-sm text-emerald-600">
          Feedback recorded.
        </div>
      )}

      {/* Diff modal */}
      {showDiff && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
          onClick={() => setShowDiff(false)}
        >
          <div
            className="bg-white rounded-lg w-full max-w-5xl max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h3 className="font-medium">Original vs Edited</h3>
              <button
                onClick={() => setShowDiff(false)}
                className="btn-ghost"
              >
                <X className="w-4 h-4" />
                Close
              </button>
            </div>
            <div className="p-4">
              <ReactDiffViewer
                oldValue={email.body}
                newValue={body}
                splitView
              />
            </div>
          </div>
        </div>
      )}

      {/* Reject modal */}
      {showRejectModal && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
          onClick={() => setShowRejectModal(false)}
        >
          <div
            className="card w-full max-w-md p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-medium mb-3">Why are you rejecting?</h3>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="e.g. Wrong vertical / not a real lead / contact bounced..."
              rows={4}
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mb-3"
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowRejectModal(false)}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={!rejectReason.trim()}
                className="btn-danger"
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
