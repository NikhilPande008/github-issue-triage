import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Investigations, sortQueue } from "./Investigations";

const base = { repository: "psf/requests", issue_number: 1, issue_title: "Title", status: "COMPLETED", asserts_failure: false, validation_reason: null, attempt_count: 1, started_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z", completed_at: "2026-07-01T00:00:00Z", duration_seconds: 1, cost_usd: 0, tracked_llm_api_cost_usd: null, tracked_llm_api_latency_ms: null, tracked_llm_api_input_tokens: null, tracked_llm_api_cached_input_tokens: null, tracked_llm_api_output_tokens: null, tracked_llm_api_cost_status: "unavailable" as const, tracked_llm_api_latency_status: "unavailable" as const, tracked_llm_api_explanation: "No tracked LLM API calls are linked to this investigation." };

it("renders API errors without crashing", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: "Database unavailable" }) }));
  render(<Investigations />);
  await waitFor(() => expect(screen.getByText(/Database unavailable/)).toBeInTheDocument());
});

it("sorts confirmed behavior gaps before other verdicts", () => {
  const items = [
    { ...base, id: "negative", classification: "WONT_REPRO" as const },
    { ...base, id: "behavior-gap", classification: "BEHAVIOR_GAP_CONFIRMED" as const },
  ];
  expect(sortQueue(items).map((item) => item.id)).toEqual(["behavior-gap", "negative"]);
});

it("renders the triage queue as the default screen", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [{ ...base, id: "run-1", classification: "BEHAVIOR_GAP_CONFIRMED" }], total: 1 }) }));
  render(<Investigations />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading triage queue");
  await waitFor(() => expect(screen.getByText("Title")).toBeInTheDocument());
});
