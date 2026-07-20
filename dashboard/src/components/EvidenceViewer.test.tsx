import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { EvidenceViewer } from "./EvidenceViewer";

it("renders formatted evidence and unavailable artifacts", () => {
  render(<EvidenceViewer artifacts={[{ id: "diff", kind: "git_diff", path: "/tmp/attempt_1/diff", available: true, content: "+assert False", size_bytes: 13, modified_at: "2026-07-17", error: null }, { id: "log", kind: "terminal_log", path: "/tmp/attempt_1/log", available: false, content: null, size_bytes: null, modified_at: null, error: "Artifact is unavailable" }]} />);
  expect(screen.getByText("+assert False")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Terminal Log (Attempt 1)"));
  expect(screen.getByText("Artifact is unavailable")).toBeInTheDocument();
});
