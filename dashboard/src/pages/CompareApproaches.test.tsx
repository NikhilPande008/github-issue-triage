import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CompareApproaches, comparisonHeadline, comparisonIntro } from "./CompareApproaches";

const base = { id: "confirmed", repository: "owner/repo", issue_number: 1, issue_title: "Recorded", status: "COMPLETED", classification: "BEHAVIOR_GAP_CONFIRMED", asserts_failure: true, validation_reason: "Recorded", attempt_count: 1, started_at: null, updated_at: "2026-07-01", completed_at: "2026-07-01", duration_seconds: null, cost_usd: null, tracked_llm_api_cost_usd: null, tracked_llm_api_latency_ms: null, tracked_llm_api_input_tokens: null, tracked_llm_api_cached_input_tokens: null, tracked_llm_api_output_tokens: null, tracked_llm_api_cost_status: "unavailable", tracked_llm_api_latency_status: "unavailable", tracked_llm_api_explanation: "Not recorded." };

it("uses bounded product language and real persisted CTA links", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [base, { ...base, id: "no-gap", classification: "WONT_REPRO", status: "COMPLETED_NO_GAP" }], page: 1, page_size: 100, total: 2 }) }));
  render(<CompareApproaches />);
  expect(screen.getByText(comparisonHeadline)).toBeInTheDocument(); expect(screen.getByText(comparisonIntro)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("link", { name: "See a confirmed evidence case" })).toHaveAttribute("href", "?id=confirmed"));
  expect(screen.getByRole("link", { name: "See a responsible no-gap outcome" })).toHaveAttribute("href", "?id=no-gap");
  expect(screen.getByText(/Whether an issue is a bug, regression, security issue/)).toBeInTheDocument();
  expect(screen.getByText(/Public dashboard views are read-only/)).toBeInTheDocument();
});

it("uses truthful unavailable representative states", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], page: 1, page_size: 100, total: 0 }) }));
  render(<CompareApproaches />);
  expect(await screen.findByText("No persisted confirmed case available.")).toBeInTheDocument();
  expect(screen.getByText("No persisted no-gap example available.")).toBeInTheDocument();
});
