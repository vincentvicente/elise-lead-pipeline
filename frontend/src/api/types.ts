// Type definitions mirroring backend Pydantic schemas (elise_leads.api.schemas).
// In a production setup we'd auto-generate these via:
//   npx openapi-typescript http://localhost:8000/openapi.json -o src/api/types.ts
// For MVP we hand-mirror so the frontend can build without a running backend.

// ---------- Lead ----------
export interface LeadListItem {
  id: string;
  name: string;
  email: string;
  company: string;
  city: string;
  state: string;
  country: string;
  status: "pending" | "processing" | "processed" | "failed";
  uploaded_at: string;
  processed_at: string | null;
  score_total: number | null;
  score_tier: "Hot" | "Warm" | "Cold" | null;
  email_source: string | null;
}

export interface LeadListResponse {
  leads: LeadListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProvenanceFact {
  fact_key: string;
  fact_value: unknown;
  source: string;
  confidence: number;
  fetched_at: string;
}

export interface ScoreOut {
  total: number;
  tier: "Hot" | "Warm" | "Cold";
  breakdown: Record<string, number>;
  reasons: string[];
}

export interface EmailOut {
  id: string;
  subject: string;
  body: string;
  source: string;
  proof_point_used: string | null;
  warnings: string[];
  hallucination_check: {
    passed?: boolean;
    severe_count?: number;
    warning_count?: number;
    issues?: Array<{
      severity: "severe" | "warning";
      category: string;
      detail: string;
    }>;
  };
  created_at: string;
}

export interface FeedbackHistoryItem {
  id: string;
  sdr_email: string;
  action: "approved" | "edited" | "rejected";
  final_subject: string | null;
  final_body: string | null;
  rejection_reason: string | null;
  review_seconds: number;
  created_at: string;
}

export interface LeadDetail {
  id: string;
  run_id: string | null;
  name: string;
  email: string;
  company: string;
  property_address: string;
  city: string;
  state: string;
  country: string;
  status: string;
  uploaded_at: string;
  processed_at: string | null;
  error_message: string | null;
  insights: string[];
  enriched: Record<string, unknown>;
  provenance: ProvenanceFact[];
  score: ScoreOut | null;
  email_draft: EmailOut | null;
  feedback: FeedbackHistoryItem[];
}

// ---------- Run ----------
export interface RunListItem {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "partial" | "crashed";
  lead_count: number;
  success_count: number;
  failure_count: number;
}

export interface RunListResponse {
  runs: RunListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface RunDetail extends RunListItem {
  report_md: string | null;
}

export interface RunTriggerResponse {
  run_id: string;
  status: string;
  message: string;
}

// ---------- Feedback ----------
export interface FeedbackCreate {
  sdr_email: string;
  action: "approved" | "edited" | "rejected";
  final_subject?: string;
  final_body?: string;
  rejection_reason?: string;
  review_seconds: number;
}

// ---------- Metrics ----------
export interface KpiCard {
  label: string;
  value: number | string;
  unit: string | null;
  delta_pct: number | null;
}

export interface TrendPoint {
  day: string; // ISO date
  leads_processed: number;
  approval_rate: number | null;
  hot_pct: number | null;
}

export interface TierDistribution {
  hot: number;
  warm: number;
  cold: number;
}

export interface RecentRunSummary {
  id: string;
  started_at: string;
  status: string;
  success_count: number;
  failure_count: number;
  lead_count: number;
}

export interface OverviewResponse {
  kpis: KpiCard[];
  trend: TrendPoint[];
  tier_distribution: TierDistribution;
  recent_runs: RecentRunSummary[];
}

export interface ApiPerformancePoint {
  api_name: string;
  total_calls: number;
  success_count: number;
  failure_count: number;
  avg_ms: number;
  p95_ms: number;
  failure_rate: number;
}

// ---------- Upload ----------
export interface UploadResponse {
  uploaded: number;
  skipped: number;
  errors: Array<{ row_number: number; error: string }>;
}
