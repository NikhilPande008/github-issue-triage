import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { InvestigationTable } from "./InvestigationTable";

const item = { id: "run-1", repository: "psf/requests", issue_number: 123, issue_title: "A real issue title", status: "COMPLETED", classification: "REPRODUCED" as const, asserts_failure: true, validation_reason: "validated", attempt_count: 1, started_at: "2026-07-17T10:00:00Z", updated_at: "2026-07-17T10:00:01Z", completed_at: "2026-07-17T10:00:01Z", duration_seconds: 1, cost_usd: 0.001, tracked_llm_api_cost_usd: 0.001, tracked_llm_api_latency_ms: 1250, tracked_llm_api_input_tokens: 100, tracked_llm_api_cached_input_tokens: 20, tracked_llm_api_output_tokens: 10, tracked_llm_api_cost_status: "available" as const, tracked_llm_api_latency_status: "available" as const, tracked_llm_api_explanation: "Tracked OpenAI API calls only; Codex excluded." };

afterEach(cleanup);

it("renders persisted investigations as real detail links", () => {
  render(<InvestigationTable items={[item]} />);
  expect(screen.getAllByRole("link", { name: /psf\/requests/i })[0]).toHaveAttribute("href", "?id=run-1");
  expect(screen.getByText("A real issue title")).toBeInTheDocument();
  expect(screen.getAllByText("—")).toHaveLength(1);
  expect(screen.getByText("1.3s")).toBeInTheDocument();
});

it("marks unlinked historical metrics unavailable without inventing a zero cost", () => {
  render(<InvestigationTable items={[{ ...item, tracked_llm_api_cost_usd: null, tracked_llm_api_latency_ms: null, tracked_llm_api_cost_status: "unavailable", tracked_llm_api_latency_status: "unavailable", tracked_llm_api_explanation: "No tracked LLM API calls are linked to this investigation." }]} />);
  expect(screen.getAllByText("—")).toHaveLength(3);
  expect(screen.getAllByTitle(/No tracked LLM API calls/)).toHaveLength(2);
});

it("explains an empty investigation list", () => {
  render(<InvestigationTable items={[]} />);
  expect(screen.getByText(/No investigations have been run yet/)).toBeInTheDocument();
});
