import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Timeline } from "./Timeline";

it("shows only persisted attempt durations", () => {
  render(<Timeline attempts={[
    { attempt_number: 1, hypothesis: "First", revision_reason: null, action: "Run pytest", result: "Evidence captured", duration_ms: 1250 },
    { attempt_number: 2, hypothesis: "Second", revision_reason: null, action: "Run pytest", result: "Evidence captured", duration_ms: null },
  ]} />);

  expect(screen.getByText("Duration:").parentElement).toHaveTextContent("Duration: 1.3s");
  expect(screen.queryByText(/Not recorded|0s/)).not.toBeInTheDocument();
});
