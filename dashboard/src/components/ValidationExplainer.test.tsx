import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ValidationExplainer } from "./ValidationExplainer";

const checks = ["changed_executable_test", "structured_junit_result", "explicit_failure", "clean_execution", "confirmation_match"].map((id) => ({ id, label: id.replaceAll("_", " "), status: "PASS" as const, explanation: "Persisted deterministic evidence passed.", artifact_kind: id === "changed_executable_test" ? "git_diff" : "structured_test_results_junit" }));

it("shows the five all-pass deterministic checks with keyboard-accessible evidence links", () => {
  render(<ValidationExplainer investigationId="run-1" data={{ version: "deterministic-validator-v1", conclusion: "BEHAVIOR_GAP_CONFIRMED", checks }} />);
  expect(screen.getByText("Behavior gap confirmed")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Open persisted evidence" })).toHaveLength(5);
  expect(screen.getAllByRole("link", { name: "Open persisted evidence" })[0]).toHaveAttribute("href", "?id=run-1#evidence");
});

it("uses non-confirming language and identifies the first blocked gate", () => {
  render(<ValidationExplainer investigationId="run-2" data={{ version: "deterministic-validator-v1", conclusion: "BEHAVIOR_GAP_NOT_ESTABLISHED", checks: [{ id: "changed_executable_test", label: "Changed executable test", status: "FAIL", explanation: "No focused test changed.", artifact_kind: "git_diff" }] }} />);
  expect(screen.getByText("No behavior gap established")).toBeInTheDocument();
  expect(screen.getByText(/does not invalidate the issue/)).toBeInTheDocument();
});
