import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { boundedCaveat, EvidenceBrief } from "./EvidenceBrief";

const base = { id: "older", repository: "psf/requests", issue_number: 7564, issue_title: "TLS behavior", test_runner: "pytest", status: "COMPLETED", classification: "BEHAVIOR_GAP_CONFIRMED", asserts_failure: true, validation_reason: "The focused assertion failed.", reproducibility_status: "STABLE", attempt_count: 1, started_at: null, updated_at: "2026-07-01T00:00:00Z", completed_at: "2026-07-01T00:00:00Z", duration_seconds: 2, cost_usd: null, tracked_llm_api_cost_usd: null, tracked_llm_api_latency_ms: null, tracked_llm_api_input_tokens: null, tracked_llm_api_cached_input_tokens: null, tracked_llm_api_output_tokens: null, tracked_llm_api_cost_status: "unavailable", tracked_llm_api_latency_status: "unavailable", tracked_llm_api_explanation: "No tracked LLM API calls are linked." };
afterEach(cleanup);

it("loads the newest confirmed investigation and its persisted evidence", async () => {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("/artifacts") ? { items: [{ id: "diff", kind: "git_diff", path: "git.diff", available: true, content: "+++ b/tests/test_tls.py\n+def test_tls():", size_bytes: 1, modified_at: null, error: null }, { id: "junit", kind: "structured_test_results_junit", path: "junit.xml", available: true, content: "<failure>missing</failure>", size_bytes: 1, modified_at: null, error: null }] } : { items: [{ ...base }, { ...base, id: "newer", completed_at: "2026-07-02T00:00:00Z" }] } })));
  render(<EvidenceBrief />);
  await waitFor(() => expect(screen.getByRole("heading", { name: "TLS behavior" })).toBeInTheDocument());
  expect(screen.getByText("tests/test_tls.py")).toBeInTheDocument();
  expect(screen.getByText("JUnit XML")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open complete evidence trail" })).toHaveAttribute("href", "?id=newer");
});

it("shows a truthful empty state when there is no confirmed investigation", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) }));
  render(<EvidenceBrief />);
  await waitFor(() => expect(screen.getByText("No confirmed investigation is available")).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "View triage queue" })).toHaveAttribute("href", "/");
});

it("uses the exact bounded caveat and makes unavailable artifacts explicit", async () => {
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("/artifacts") ? { items: [{ id: "diff", kind: "git_diff", path: "git.diff", available: false, content: null, size_bytes: null, modified_at: null, error: "Not retained" }] } : { items: [base] } })));
  render(<EvidenceBrief />);
  await waitFor(() => expect(screen.getAllByText(boundedCaveat).length).toBeGreaterThan(0));
  expect(screen.getByText(/Git diff unavailable/)).toBeInTheDocument();
  expect(screen.getByText(/JUnit XML unavailable/)).toBeInTheDocument();
});
