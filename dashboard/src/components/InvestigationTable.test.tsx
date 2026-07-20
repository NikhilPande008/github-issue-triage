import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { InvestigationTable } from "./InvestigationTable";

const item = { id: "run-1", repository: "psf/requests", issue_number: 123, status: "COMPLETED", classification: "REPRODUCED" as const, asserts_failure: true, validation_reason: "validated", attempt_count: 1, started_at: "2026-07-17T10:00:00Z", updated_at: "2026-07-17T10:00:01Z", duration_seconds: 1, cost_usd: 0.001 };

it("renders persisted investigations and opens one", () => {
  const onOpen = vi.fn();
  render(<InvestigationTable items={[item]} onOpen={onOpen} />);
  expect(screen.getByText("psf/requests")).toBeInTheDocument();
  fireEvent.click(screen.getByText("psf/requests"));
  expect(onOpen).toHaveBeenCalledWith("run-1");
});

it("explains an empty investigation list", () => {
  render(<InvestigationTable items={[]} onOpen={vi.fn()} />);
  expect(screen.getByText(/No investigations have been run yet/)).toBeInTheDocument();
});
