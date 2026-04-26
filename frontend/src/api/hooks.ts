// Typed TanStack Query hooks — one per backend endpoint.
//
// Conventions:
// - Query keys are arrays starting with the resource name + filter kwargs.
// - Polling: enabled only on detail views where status='running' to avoid
//   unnecessary background load.

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { api } from "./client";
import type {
  ApiPerformancePoint,
  FeedbackCreate,
  FeedbackHistoryItem,
  LeadDetail,
  LeadListResponse,
  OverviewResponse,
  RunDetail,
  RunListResponse,
  RunTriggerResponse,
  UploadResponse,
} from "./types";

// ---------- Metrics ----------
export function useOverview(
  options?: Partial<UseQueryOptions<OverviewResponse>>
) {
  return useQuery<OverviewResponse>({
    queryKey: ["metrics", "overview"],
    queryFn: () => api.get("/api/v1/metrics/overview"),
    refetchInterval: 30_000, // refresh KPIs every 30s on the Overview page
    ...options,
  });
}

export function useApiPerformance(days = 30) {
  return useQuery<ApiPerformancePoint[]>({
    queryKey: ["metrics", "api-performance", days],
    queryFn: () => api.get(`/api/v1/metrics/api-performance?days=${days}`),
  });
}

// ---------- Runs ----------
export function useRuns(page = 1, pageSize = 20, status?: string) {
  const qs = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (status) qs.set("status", status);
  return useQuery<RunListResponse>({
    queryKey: ["runs", page, pageSize, status],
    queryFn: () => api.get(`/api/v1/runs?${qs.toString()}`),
  });
}

export function useRun(runId: string | undefined) {
  return useQuery<RunDetail>({
    queryKey: ["runs", runId],
    queryFn: () => api.get(`/api/v1/runs/${runId}`),
    enabled: !!runId,
    // Poll while the run is still running (PART_A v2 §8.3)
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === "running" ? 3_000 : false;
    },
  });
}

export function useTriggerRun() {
  const qc = useQueryClient();
  return useMutation<RunTriggerResponse>({
    mutationFn: () => api.post("/api/v1/runs/trigger"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

// ---------- Leads ----------
export function useLeads(opts: {
  page?: number;
  pageSize?: number;
  tier?: string;
  status?: string;
  runId?: string;
} = {}) {
  const qs = new URLSearchParams();
  qs.set("page", String(opts.page ?? 1));
  qs.set("page_size", String(opts.pageSize ?? 50));
  if (opts.tier) qs.set("tier", opts.tier);
  if (opts.status) qs.set("status", opts.status);
  if (opts.runId) qs.set("run_id", opts.runId);

  return useQuery<LeadListResponse>({
    queryKey: ["leads", opts],
    queryFn: () => api.get(`/api/v1/leads?${qs.toString()}`),
  });
}

export function useLead(leadId: string | undefined) {
  return useQuery<LeadDetail>({
    queryKey: ["leads", leadId],
    queryFn: () => api.get(`/api/v1/leads/${leadId}`),
    enabled: !!leadId,
  });
}

// ---------- Feedback ----------
export function useSubmitFeedback(leadId: string) {
  const qc = useQueryClient();
  return useMutation<FeedbackHistoryItem, Error, FeedbackCreate>({
    mutationFn: (body) =>
      api.post(`/api/v1/leads/${leadId}/feedback`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads", leadId] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

// ---------- Upload ----------
export function useUploadCsv() {
  const qc = useQueryClient();
  return useMutation<UploadResponse, Error, File>({
    mutationFn: (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post("/api/v1/uploads", fd);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
