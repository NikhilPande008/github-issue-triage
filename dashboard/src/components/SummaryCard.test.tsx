import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { SummaryCard } from "./SummaryCard";
import type { InvestigationSummary } from "../services/api";

const summary: InvestigationSummary = {
  id: "run", repository: "psf/requests", issue_number: 7564, issue_title: "TLS", status: "COMPLETED", classification: "BEHAVIOR_GAP_CONFIRMED", asserts_failure: true, validation_reason: null, attempt_count: 1, started_at: null, updated_at: null, completed_at: null, duration_seconds: 2, cost_usd: 0, tracked_llm_api_cost_usd: 0.004275, tracked_llm_api_latency_ms: 6835, tracked_llm_api_input_tokens: 873, tracked_llm_api_cached_input_tokens: 0, tracked_llm_api_output_tokens: 567, tracked_llm_api_cost_status: "available", tracked_llm_api_latency_status: "available", tracked_llm_api_explanation: "Tracked OpenAI API calls only; Codex usage is excluded because exact Codex billing data is unavailable.", total_duration_seconds: 2, input_tokens: 873, cached_input_tokens: 0, output_tokens: 567, total_tokens: 1440, cache_hit_percent: 0, latency_ms: 6835,
};

it("shows the Codex exclusion caveat alongside available tracked metrics", () => {
  render(<SummaryCard summary={summary} />);
  expect(screen.getByText("$0.0043")).toBeInTheDocument();
  expect(screen.getByText("6.8s")).toBeInTheDocument();
  expect(screen.getByText(/Codex usage is excluded/)).toBeInTheDocument();
});
