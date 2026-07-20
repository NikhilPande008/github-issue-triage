export type Classification = "REPRODUCED" | "NEEDS_INFO" | "WONT_REPRO" | "NOT_A_BUG" | "DUPLICATE";

export interface Investigation {
  id: string;
  repository: string;
  issue_number: number;
  status: string;
  classification: Classification | null;
  asserts_failure: boolean;
  validation_reason: string | null;
  attempt_count: number;
  started_at: string | null;
  updated_at: string | null;
  duration_seconds: number | null;
  cost_usd: number;
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
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_hit_percent: number | null;
  cost_usd: number;
  latency_ms: number;
}

const baseUrl = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`);
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const api = {
  investigations: (page = 1, classification?: Classification) =>
    request<{ items: Investigation[]; page: number; page_size: number; total: number }>(
      `/investigations?page=${page}${classification ? `&classification=${classification}` : ""}`,
    ),
  investigation: (id: string) => request<Investigation>(`/investigations/${id}`),
  timeline: (id: string) => request<{ items: TimelineAttempt[] }>(`/investigations/${id}/timeline`),
  artifacts: (id: string) => request<{ items: EvidenceArtifact[] }>(`/investigations/${id}/artifacts`),
  summary: (id: string) => request<InvestigationSummary>(`/investigations/${id}/summary`),
};
