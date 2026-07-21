import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { NextActions } from "./NextActions";
import type { EvidenceArtifact, Investigation } from "../services/api";

const base: Investigation = { id: "run-1", repository: "owner/repo", issue_number: 12, issue_title: "Recorded issue", status: "COMPLETED", classification: "BEHAVIOR_GAP_CONFIRMED", asserts_failure: true, validation_reason: "Focused failure recorded.", attempt_count: 1, started_at: null, updated_at: null, completed_at: null, duration_seconds: null, cost_usd: null, tracked_llm_api_cost_usd: null, tracked_llm_api_latency_ms: null, tracked_llm_api_input_tokens: null, tracked_llm_api_cached_input_tokens: null, tracked_llm_api_output_tokens: null, tracked_llm_api_cost_status: "unavailable", tracked_llm_api_latency_status: "unavailable", tracked_llm_api_explanation: "Not recorded." };
const artifact = (kind: string, content: string | null = "{}"): EvidenceArtifact => ({ id: kind, kind, path: `/tmp/${kind}`, available: true, content, size_bytes: 1, modified_at: null, error: null });

it("gives confirmed evidence links and advisory, non-remediating guidance", () => {
  render(<NextActions summary={base} artifacts={[artifact("git_diff"), artifact("structured_test_results_junit"), artifact("reproducibility_manifest")]} semanticReview={{ packet_status: "AVAILABLE", reason: null, review: null }} />);
  expect(screen.getByText("Maintainer next action")).toBeInTheDocument();
  expect(screen.getByText(/Review the focused failing test/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open changed test and diff" })).toHaveAttribute("href", "?id=run-1#evidence");
  expect(screen.getByRole("link", { name: "Open semantic-fidelity review" })).toHaveAttribute("href", "?id=run-1#semantic-review");
  expect(screen.getByText(/not an automated issue decision/)).toBeInTheDocument();
  expect(screen.queryByText(/fix the bug/i)).not.toBeInTheDocument();
});

it("uses persisted extraction for a copyable NEEDS_INFO preview", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined); Object.assign(navigator, { clipboard: { writeText } });
  render(<NextActions summary={{ ...base, classification: "NEEDS_INFO", status: "COMPLETED_NO_GAP" }} artifacts={[artifact("extraction_json", '{"missing_info":["Python version"]}')] } />);
  expect(screen.getByText("Request the missing reproduction details")).toBeInTheDocument();
  expect(screen.getByText("Preview only — not posted to GitHub.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Copy maintainer-ready reply" }));
  expect(await screen.findByText("Copied to clipboard.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /post|retry|run/i })).not.toBeInTheDocument();
});

it("uses conservative no-gap and non-defect language", () => {
  const { rerender } = render(<NextActions summary={{ ...base, classification: "WONT_REPRO", status: "COMPLETED_NO_GAP" }} artifacts={[]} />);
  expect(screen.getByRole("heading", { name: "No behavior gap established" })).toBeInTheDocument();
  expect(screen.queryByText("WONT_REPRO")).not.toBeInTheDocument();
  rerender(<NextActions summary={{ ...base, classification: "NOT_A_BUG" }} artifacts={[]} />);
  expect(screen.getByText("Possible non-defect framing — human review required")).toBeInTheDocument();
  expect(screen.getByText(/not a final disposition/)).toBeInTheDocument();
});

it("keeps setup, flaky, and running states operationally inconclusive", () => {
  const { rerender } = render(<NextActions summary={{ ...base, classification: null, status: "FAILED", validation_reason: "Setup dependency failed; SANDBOX_SETUP_COMMAND recorded." }} artifacts={[artifact("reproducibility_manifest", '{"setup_command":"pip install"}')] } />);
  expect(screen.getByRole("heading", { name: "Operationally inconclusive" })).toBeInTheDocument();
  expect(screen.getByText("triage preflight --repository owner/repo")).toBeInTheDocument();
  expect(screen.getByText(/explicit repository setup command/)).toBeInTheDocument();
  rerender(<NextActions summary={{ ...base, classification: null, status: "RUNNING", reproducibility_status: "NOT_CONFIRMED", validation_reason: "Flaky confirmation." }} artifacts={[]} />);
  expect(screen.getByText(/Review flaky confirmation evidence/)).toBeInTheDocument();
  expect(screen.getByText(/Wait for the active investigation to finish/)).toBeInTheDocument();
});
