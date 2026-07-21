import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { InvestigationDetail } from "./InvestigationDetail";

const summary = {
  id: "run-1", repository: "psf/requests", issue_number: 7564, issue_title: "TLS", status: "COMPLETED",
  classification: "REPRODUCED" as const, asserts_failure: true, validation_reason: "A new assertion failed in tests/test_requests.py.",
  attempt_count: 1, started_at: null, updated_at: null, completed_at: null, duration_seconds: 2, cost_usd: 0.004,
  tracked_llm_api_cost_usd: 0.004, tracked_llm_api_latency_ms: 1000, tracked_llm_api_input_tokens: 1,
  tracked_llm_api_cached_input_tokens: 0, tracked_llm_api_output_tokens: 1, tracked_llm_api_cost_status: "available" as const,
  tracked_llm_api_latency_status: "available" as const, tracked_llm_api_explanation: "Tracked OpenAI API calls only.",
  total_duration_seconds: 2, input_tokens: 1, cached_input_tokens: 0, output_tokens: 1, total_tokens: 2,
  cache_hit_percent: 0, latency_ms: 1000,
};

it("explains deterministic validation while keeping the evidence reason visible", async () => {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const payload = url.includes("/summary") ? summary : url.includes("/timeline")
      ? { items: [{ attempt_number: 1, hypothesis: "Focused test", revision_reason: null, action: "pytest", result: "Evidence captured", duration_ms: null }] }
      : { items: [] };
    return Promise.resolve({ ok: true, json: async () => payload });
  }));

  render(<InvestigationDetail id="run-1" />);
  await waitFor(() => expect(screen.getByText(summary.validation_reason)).toBeInTheDocument());
  expect(screen.getByLabelText("About assertsFailure")).toBeInTheDocument();
  expect(screen.getByLabelText("About validation reason")).toBeInTheDocument();
  expect(screen.getByText(/The deterministic validator’s evidence-based reason/)).toBeInTheDocument();
  expect(screen.queryByText(/Duration: Not recorded|Duration: 0s/)).not.toBeInTheDocument();
});
