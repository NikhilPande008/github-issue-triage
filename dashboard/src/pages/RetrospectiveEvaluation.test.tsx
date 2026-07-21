import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { evaluationCaveat, RetrospectiveEvaluation } from "./RetrospectiveEvaluation";

it("shows the honest empty state", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "no_data", dataset: { schema_version: "retrospective-v1", captured_at: null, excluded_case_count: 0, cases: [] } }) }));
  render(<RetrospectiveEvaluation />);
  expect(await screen.findByText("No independently curated retrospective cases are available in this demo.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Evidence Results" })).toHaveAttribute("href", "?results=1");
});

it("renders a source-backed case with local evidence and unavailable metrics", async () => {
  const item = { case_id: "case", repository: "owner/repo", issue_number: 1, issue_url: "https://github.com/owner/repo/issues/1", title: "Bounded", investigation_id: "run-1", terminal_status: "COMPLETED", classification: "BEHAVIOR_GAP_CONFIRMED", assertsFailure: true, validation_reason: "Focused failure", tracked_openai_cost: null, tracked_openai_latency: null, codex_wall_time: null, external_support: "AMBIGUOUS", evaluator_note: "Public history is ambiguous.", sources: [{ url: "https://github.com/owner/repo/issues/1#comment", source_type: "MAINTAINER_COMMENT", title: "Maintainer note", captured_at: "2026-07-21" }], inclusion_rationale: "Source-backed", limitations: "Selected sample." };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "available", dataset: { schema_version: "retrospective-v1", captured_at: "2026-07-21", excluded_case_count: 1, cases: [item] } }) }));
  render(<RetrospectiveEvaluation />);
  await waitFor(() => expect(screen.getByText(evaluationCaveat)).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "Open local evidence" })).toHaveAttribute("href", "?id=run-1");
  expect(screen.getByRole("link", { name: /MAINTAINER COMMENT/ })).toHaveAttribute("href", item.sources[0].url);
  expect(screen.getByText(/Tracked OpenAI cost: Unavailable/)).toBeInTheDocument();
  expect(screen.queryByText(/\d+(?:\.\d+)?%/)).not.toBeInTheDocument();
});
