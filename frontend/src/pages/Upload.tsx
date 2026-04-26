import { useState, type DragEvent, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Play, UploadCloud } from "lucide-react";
import { useTriggerRun, useUploadCsv } from "@/api/hooks";
import { PageHeader } from "@/components/PageHeader";
import { cn } from "@/lib/utils";

const REQUIRED_COLUMNS = [
  "name",
  "email",
  "company",
  "property_address",
  "city",
  "state",
  "country",
];

export function Upload() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const upload = useUploadCsv();
  const trigger = useTriggerRun();

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
  };

  const submit = async () => {
    if (!file) return;
    upload.mutate(file);
  };

  const triggerNow = () => {
    trigger.mutate(undefined, {
      onSuccess: (resp) => {
        navigate(`/runs/${resp.run_id}`);
      },
    });
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <PageHeader
        title="Upload leads"
        subtitle="CSV with the 7 standard fields. Pending leads are processed by the next cron run, or trigger one now."
      />

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "card border-2 border-dashed p-10 text-center transition-colors",
          dragOver
            ? "border-blue-500 bg-blue-50"
            : "border-slate-300 hover:border-slate-400"
        )}
      >
        <UploadCloud className="w-10 h-10 mx-auto text-slate-400" />
        <div className="mt-3 text-sm text-slate-600">
          {file ? (
            <>
              <span className="font-medium text-slate-900">{file.name}</span>{" "}
              ({(file.size / 1024).toFixed(1)} KB)
            </>
          ) : (
            <>
              Drag a CSV here, or{" "}
              <label className="text-blue-700 hover:underline cursor-pointer">
                browse
                <input
                  type="file"
                  accept=".csv"
                  onChange={onPick}
                  className="hidden"
                />
              </label>
            </>
          )}
        </div>
        <div className="mt-3 text-xs text-slate-500">
          Required columns:{" "}
          <span className="font-mono">{REQUIRED_COLUMNS.join(", ")}</span>
        </div>
      </div>

      {/* Submit */}
      <div className="mt-4 flex gap-2 justify-end">
        {file && (
          <button
            className="btn-secondary"
            onClick={() => {
              setFile(null);
              upload.reset();
            }}
          >
            Clear
          </button>
        )}
        <button
          className="btn-primary"
          disabled={!file || upload.isPending}
          onClick={submit}
        >
          {upload.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <UploadCloud className="w-4 h-4" />
          )}
          Upload
        </button>
      </div>

      {/* Result */}
      {upload.error && (
        <div className="card p-3 mt-4 bg-rose-50 border-rose-200 text-rose-700 text-sm">
          {(upload.error as Error).message}
        </div>
      )}

      {upload.data && (
        <div className="card p-4 mt-4">
          <div className="text-sm">
            <span className="font-medium text-emerald-700">
              {upload.data.uploaded}
            </span>{" "}
            row(s) accepted
            {upload.data.skipped > 0 && (
              <>
                ,{" "}
                <span className="font-medium text-rose-600">
                  {upload.data.skipped}
                </span>{" "}
                skipped
              </>
            )}
            .
          </div>

          {upload.data.errors.length > 0 && (
            <details className="mt-2">
              <summary className="text-xs text-slate-500 cursor-pointer">
                Show errors ({upload.data.errors.length})
              </summary>
              <ul className="mt-2 space-y-1 text-xs text-slate-600">
                {upload.data.errors.map((e, i) => (
                  <li key={i} className="font-mono">
                    Row {e.row_number}: {e.error}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className="mt-4 flex gap-2">
            <button
              onClick={triggerNow}
              disabled={trigger.isPending}
              className="btn-success"
            >
              {trigger.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Process now
            </button>
            <button
              onClick={() => navigate("/leads?status=pending")}
              className="btn-secondary"
            >
              View pending leads →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
