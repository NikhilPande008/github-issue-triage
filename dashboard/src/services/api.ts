export type Classification = "BEHAVIOR_GAP_CONFIRMED" | "NEEDS_INFO" | "WONT_REPRO" | "NOT_A_BUG" | "DUPLICATE";

export interface Investigation {
  id: string;
  repository: string;
  issue_number: number;
  issue_title: string | null;
  test_runner?: string;
  status: string;
  classification: Classification | null;
  asserts_failure: boolean;
  validation_reason: string | null;
  validation_provenance?: string | null;
  reproducibility_status?: "STABLE" | "NOT_CONFIRMED" | "LEGACY";
  budget_status?: string;
  budget_reason?: string | null;
  codex_invocation_count?: number;
  codex_wall_seconds?: number;
  codex_wall_cap_seconds?: number | null;
  attempt_count: number;
  started_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  cost_usd: number | null;
  tracked_llm_api_cost_usd: number | null;
  tracked_llm_api_latency_ms: number | null;
  tracked_llm_api_input_tokens: number | null;
  tracked_llm_api_cached_input_tokens: number | null;
  tracked_llm_api_output_tokens: number | null;
  tracked_llm_api_cost_status: "available" | "unavailable";
  tracked_llm_api_latency_status: "available" | "unavailable";
  tracked_llm_api_explanation: string;
  webhook_job?: WebhookJob;
}

export interface WebhookJob {
  id: string;
  delivery_id: string;
  status: string;
  comment_status: string;
  comment_reason: string | null;
  comment_body: string | null;
  is_preview: boolean;
  github_comment_id: string | null;
}

export interface RelatedInvestigation {
  investigation_id: string;
  repository: string;
  issue_number: number;
  classification: Classification | null;
  status: string;
  similarity_score: number;
  matched_signals: string[];
  label: string;
}

export interface TimelineAttempt {
  attempt_number: number;
  hypothesis: string;
  revision_reason: string | null;
  action: string;
  result: string;
  duration_ms: number | null;
}

export interface EvidenceArtifact {
  id: string;
  kind: string;
  path: string;
  available: boolean;
  content: string | null;
  size_bytes: number | null;
  modified_at: string | null;
  error: string | null;
}

export interface InvestigationSummary extends Investigation {
  total_duration_seconds: number | null;
  input_tokens: number | null;
  cached_input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cache_hit_percent: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
}

const baseUrl = import.meta.env.VITE_API_URL ?? "";

let csrfToken: string | undefined;
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (csrfToken && init?.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export interface PilotUser { reviewer: { external_id: string; cohort: string; posting_approver: boolean; repositories: string[] }; csrf_token: string; expires_at: string; }
export interface ReviewQueueItem { investigation_id: string; repository: string; issue_number: number; issue_title: string | null; classification: string; asserts_failure: boolean; consensus_state: string; coverage: Record<string, number>; comment_status: string | null; posting_eligibility: string; review_age_started_at: string | null; tracked_openai_cost_usd: number | null; codex_wall_seconds: number; packet_id: string; packet_hash: string; packet_version: number; }
export interface WeeklyReport { id: string; report_hash: string; generated_at: string; report: Record<string, unknown>; }
export type ReviewOutcome = "ALIGNED" | "UNCLEAR" | "MISALIGNED";
export interface SemanticEvidence { claim: { available: boolean; summary?: string | null; expected_behavior?: string | null; actual_behavior?: string | null; missing_information?: string[] }; generated_test: { hypothesis?: string | null; available: boolean; changed_test_paths?: string[]; assertion_lines?: string[]; diff_excerpt?: string; reason?: string }; junit: { available: boolean; testcase?: string | null; failure?: string | null; reason?: string }; validation_reason?: string | null; }
export interface SemanticReview { packet_status: "AVAILABLE" | "NOT_ISSUED" | "UNAVAILABLE"; reason: string | null; review: { packet_version: number; evidence: SemanticEvidence; state: string; display_state: string; coverage: Record<string, number> } | null; }
export interface PilotPacket { id: string; version: number; investigation_id: string; repository: string; issue_number: number; issue_title: string | null; evidence: SemanticEvidence; state: string; display_state: string; coverage: Record<string, number>; }
export interface AssessmentInput { extraction_aligned: string; test_aligned: string; failure_supports_signal: string; public_comment_appropriate: string; confidence: string; rationale?: string; reason_tags?: string[]; supersedes_assessment_id?: string | null; }
export interface ValidationCheck { id: string; label: string; status: "PASS" | "FAIL" | "UNAVAILABLE" | "NOT_APPLICABLE"; explanation: string; artifact_kind: string | null; }
export interface ValidationExplainer { version: string; conclusion: "BEHAVIOR_GAP_CONFIRMED" | "BEHAVIOR_GAP_NOT_ESTABLISHED"; checks: ValidationCheck[]; }
export interface LiveDemoConfig { enabled: boolean; repositories: string[]; issue_numbers: number[]; max_concurrent_runs: number; reason: string | null; }
export interface LiveDemoProgress { id: string; status: string; stage: string; detail: string; terminal: boolean; investigation_id: string | null; }
export interface RetrospectiveSource { url: string; source_type: string; title: string; captured_at: string; }
export interface RetrospectiveCase { case_id: string; repository: string; issue_number: number; issue_url: string; title: string; historical_state: string; investigation_id: string | null; terminal_status: string | null; classification: string | null; assertsFailure: boolean | null; validation_reason: string | null; tracked_openai_cost: number | null; tracked_openai_latency: number | null; codex_wall_time: number | null; external_support: string; evaluator_note: string; sources: RetrospectiveSource[]; inclusion_rationale: string; limitations: string; }
export interface RetrospectiveEvaluation { status: "available" | "no_data" | "invalid"; reason?: string; dataset?: { schema_version: string; captured_at: string | null; excluded_case_count: number; exclusion_rationale?: string | null; limitations?: string[]; cases: RetrospectiveCase[] }; }

export const api = {
  investigations: (page = 1, classification?: Classification, pageSize = 100) =>
    request<{ items: Investigation[]; page: number; page_size: number; total: number }>(
      `/investigations?page=${page}&page_size=${pageSize}${classification ? `&classification=${classification}` : ""}`,
    ),
  investigation: (id: string) => request<Investigation>(`/investigations/${id}`),
  timeline: (id: string) => request<{ items: TimelineAttempt[] }>(`/investigations/${id}/timeline`),
  artifacts: (id: string) => request<{ items: EvidenceArtifact[] }>(`/investigations/${id}/artifacts`),
  summary: (id: string) => request<InvestigationSummary>(`/investigations/${id}/summary`),
  related: (id: string) => request<{ items: RelatedInvestigation[]; available: boolean; reason: string | null }>(`/investigations/${id}/related`),
  semanticReview: (id: string) => request<SemanticReview>(`/investigations/${id}/semantic-review`),
  validationExplainer: (id: string) => request<ValidationExplainer>(`/investigations/${id}/validation-explainer`),
  liveDemoConfig: () => request<LiveDemoConfig>("/demo/live/config"),
  startLiveDemo: (repository: string, issue_number: number, token?: string) => request<{ id: string; status: string }>("/demo/live/investigations", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { "X-Live-Demo-Token": token } : {}) }, body: JSON.stringify({ repository, issue_number, confirm_live_run: true }) }),
  liveDemoProgress: (id: string) => request<LiveDemoProgress>(`/demo/live/investigations/${id}`),
  retrospectiveEvaluation: () => request<RetrospectiveEvaluation>("/evaluation/retrospective"),
  pilotLogin: async (reviewer_id: string, token: string) => { const user = await request<PilotUser>("/pilot-review/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewer_id, token }) }); csrfToken = user.csrf_token; return user; },
  pilotMe: async () => { const user = await request<PilotUser>("/pilot-review/me"); csrfToken = user.csrf_token; return user; },
  pilotLogout: async () => { await request("/pilot-review/logout", { method: "POST" }); csrfToken = undefined; },
  reviewQueue: () => request<{ items: ReviewQueueItem[] }>("/pilot-review/queue"),
  pilotPacket: (id: string) => request<{ packet: PilotPacket }>(`/pilot-review/packets/${id}`),
  submitAssessment: (packetId: string, payload: AssessmentInput) => request<{ id: string; derived_review_outcome: ReviewOutcome }>(`/review-packets/${packetId}/assessments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  weeklyReport: (repository: string, weekStart: string) => request<WeeklyReport>(`/pilot-review/reports/weekly?repository=${encodeURIComponent(repository)}&week_start=${encodeURIComponent(weekStart)}`),
  weeklyReportCsvUrl: (repository: string, weekStart: string) => `${baseUrl}/pilot-review/reports/weekly/export.csv?repository=${encodeURIComponent(repository)}&week_start=${encodeURIComponent(weekStart)}`,
};
