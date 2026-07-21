import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MaintainerReply } from "./MaintainerReply";
import type { EvidenceArtifact } from "../services/api";

const artifact = (content: string | null, available = true): EvidenceArtifact => ({ id: "extraction", kind: "extraction_json", path: "/tmp/extraction.json", available, content, size_bytes: null, modified_at: null, error: null });

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("appears only for NEEDS_INFO and turns persisted missing info into copyable text", () => {
  const { rerender } = render(<MaintainerReply classification="NEEDS_INFO" artifacts={[artifact('{"missing_info":[" Python version ", "python   version", "- minimal script", ""]}')]} />);
  expect(screen.getByText("Copyable reply preview")).toBeInTheDocument();
  expect(screen.getByText(/- Python version/)).toBeInTheDocument();
  expect(screen.getByText(/- minimal script/)).toBeInTheDocument();
  expect(screen.getAllByText(/Python version/i)).toHaveLength(1);
  expect(screen.getByText("Preview only — not posted to GitHub.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /post|submit|publish/i })).not.toBeInTheDocument();
  rerender(<MaintainerReply classification="BEHAVIOR_GAP_CONFIRMED" artifacts={[artifact('{"missing_info":["Python version"]}')]} />);
  expect(screen.queryByText("Copyable reply preview")).not.toBeInTheDocument();
});

it("uses the conservative fallback when persisted missing info is absent or unusable", () => {
  render(<MaintainerReply classification="NEEDS_INFO" artifacts={[artifact("not json")]} />);
  expect(screen.getByText(/- the affected package and version/)).toBeInTheDocument();
  expect(screen.getByText(/- your Python version and operating system/)).toBeInTheDocument();
  expect(screen.getByText(/- a minimal reproducible example/)).toBeInTheDocument();
  expect(screen.getByText(/- the complete traceback/)).toBeInTheDocument();
});

it("reports successful copying", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  render(<MaintainerReply classification="NEEDS_INFO" artifacts={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy maintainer-ready reply" }));
  expect(await screen.findByText("Copied to clipboard.")).toBeInTheDocument();
  expect(writeText).toHaveBeenCalledWith(expect.stringContaining("Thanks for the report."));
});
