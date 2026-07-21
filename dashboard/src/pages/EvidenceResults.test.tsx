import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { outcomeDistribution, representativeEvidence, resultsCaveat, EvidenceResults } from "./EvidenceResults";
import type { Investigation } from "../services/api";

const base: Investigation = { id: "base", repository: "org/repo", issue_number: 1, issue_title: "Recorded issue", test_runner: "pytest", status: "COMPLETED", classification: "BEHAVIOR_GAP_CONFIRMED", asserts_failure: true, validation_reason: "Recorded validation reason.", attempt_count: 1, started_at: null, updated_at: "2026-07-01T00:00:00Z", completed_at: "2026-07-01T00:00:00Z", duration_seconds: 1, cost_usd: null, tracked_llm_api_cost_usd: null, tracked_llm_api_latency_ms: null, tracked_llm_api_input_tokens: null, tracked_llm_api_cached_input_tokens: null, tracked_llm_api_output_tokens: null, tracked_llm_api_cost_status: "unavailable", tracked_llm_api_latency_status: "unavailable", tracked_llm_api_explanation: "Not recorded." };
afterEach(cleanup);

it("separates terminal outcomes, operational failures, and incomplete records without double counting", () => {
  const items: Investigation[] = [
    base, { ...base, id: "needs", classification: "NEEDS_INFO", status: "COMPLETED_NO_GAP" }, { ...base, id: "wont", classification: "WONT_REPRO", status: "COMPLETED_NO_GAP" }, { ...base, id: "not-bug", classification: "NOT_A_BUG" },
    { ...base, id: "failed", classification: null, status: "FAILED" }, { ...base, id: "classified-failed", classification: "NEEDS_INFO", status: "FAILED" }, { ...base, id: "running", classification: null, status: "RUNNING" }, { ...base, id: "unclassified-completed", classification: null, status: "COMPLETED" },
  ];
  expect(outcomeDistribution(items)).toEqual({ confirmed: 1, needsInfo: 2, wontRepro: 1, notABug: 1, other: 0, operationalFailures: 1, incomplete: 2 });
});

it("chooses the newest real representative for each requested outcome", () => {
  const examples = representativeEvidence([base, { ...base, id: "new-confirmed", completed_at: "2026-07-03T00:00:00Z" }, { ...base, id: "needs", classification: "NEEDS_INFO", status: "COMPLETED_NO_GAP" }, { ...base, id: "no-gap", classification: "WONT_REPRO", status: "COMPLETED_NO_GAP" }]);
  expect(examples.confirmed?.id).toBe("new-confirmed"); expect(examples.needsInfo?.id).toBe("needs"); expect(examples.noGap?.id).toBe("no-gap");
});

it("renders persisted results, caveat language, and evidence-detail links", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [base, { ...base, id: "needs", classification: "NEEDS_INFO", status: "COMPLETED_NO_GAP" }, { ...base, id: "wont", classification: "WONT_REPRO", status: "COMPLETED_NO_GAP" }], page: 1, page_size: 100, total: 3 }) }));
  render(<EvidenceResults />);
  await waitFor(() => expect(screen.getByRole("heading", { name: "Evidence Results" })).toBeInTheDocument());
  expect(screen.getByText(resultsCaveat)).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Open evidence detail/ })[0]).toHaveAttribute("href", "?id=base");
  expect(screen.getByLabelText("Outcome distribution")).toHaveTextContent("Behavior gap confirmed");
});

it("shows truthful no-data and unavailable states", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], page: 1, page_size: 100, total: 0 }) }));
  const view = render(<EvidenceResults />);
  await waitFor(() => expect(screen.getByText("No persisted investigations yet")).toBeInTheDocument());
  view.unmount();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: "Database unavailable" }) }));
  render(<EvidenceResults />);
  await waitFor(() => expect(screen.getByText("Evidence Results unavailable")).toBeInTheDocument());
  expect(screen.getByText(/Database unavailable/)).toBeInTheDocument();
});
