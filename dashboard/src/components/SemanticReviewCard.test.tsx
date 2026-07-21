import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SemanticReviewCard } from "./SemanticReviewCard";

const available = { packet_status: "AVAILABLE" as const, reason: null, review: { packet_version: 1, state: "PENDING_REVIEW", display_state: "Awaiting required review coverage", coverage: { MAINTAINER: 1, INDEPENDENT_ENGINEER: 0 }, evidence: { claim: { available: true, summary: "A bounded claim.", expected_behavior: "Expected", actual_behavior: "Actual", missing_information: ["Version"] }, generated_test: { available: true, hypothesis: "Exercise the bounded claim.", changed_test_paths: ["tests/test_target.py"], assertion_lines: ["+    assert result == expected"] }, junit: { available: false, reason: "The structured JUnit artifact is unavailable." }, validation_reason: "Structured failure recorded." } } };
afterEach(cleanup);

it("shows bounded public evidence and aggregate review state without reviewer data", () => {
  render(<SemanticReviewCard data={available} loading={false} />);
  expect(screen.getByRole("heading", { name: "Semantic fidelity review" })).toBeInTheDocument();
  expect(screen.getByText("A bounded claim.")).toBeInTheDocument();
  expect(screen.getByText((text) => text.includes("assert result == expected"))).toBeInTheDocument();
  expect(screen.getByText(/1 maintainer/)).toBeInTheDocument();
  expect(screen.queryByText(/reviewer-a|internal rationale/i)).not.toBeInTheDocument();
});

it("is honest when no immutable review packet was issued", () => {
  render(<SemanticReviewCard data={{ packet_status: "NOT_ISSUED", reason: "No immutable review packet has been issued for this investigation.", review: null }} loading={false} />);
  expect(screen.getByText("Not issued")).toBeInTheDocument();
  expect(screen.getByText(/Semantic review does not change deterministic validation/)).toBeInTheDocument();
});

it("shows an unavailable packet state without inventing evidence", () => {
  render(<SemanticReviewCard data={{ packet_status: "UNAVAILABLE", reason: "Packet issuance failed.", review: null }} loading={false} />);
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
  expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent?.includes("Packet issuance failed.") === true)).toBeInTheDocument();
});
