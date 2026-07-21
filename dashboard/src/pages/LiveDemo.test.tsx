import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { LiveDemo } from "./LiveDemo";

it("shows no usable action when the deployment disables the live demo", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: false, repositories: [], issue_numbers: [], max_concurrent_runs: 1, reason: "Live demo is disabled for this deployment." }) }));
  render(<LiveDemo />);
  expect(await screen.findByText("Live demo is disabled for this deployment.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /start bounded/i })).not.toBeInTheDocument();
});

it("requires acknowledgement, keeps the token out of the URL, and links completed evidence", async () => {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve({ ok: true, json: async () => url.endsWith("/config") ? { enabled: true, repositories: ["owner/repo"], issue_numbers: [7], max_concurrent_runs: 1, reason: null } : init?.method === "POST" ? { id: "job-1", status: "queued" } : { id: "job-1", status: "succeeded", stage: "completed_outcome", detail: "Bounded investigation completed", terminal: true, investigation_id: "run-1" } })));
  render(<LiveDemo />);
  const start = await screen.findByRole("button", { name: "Start bounded investigation" });
  expect(start).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I acknowledge this bounded/i));
  fireEvent.change(screen.getByLabelText(/Operator token/i), { target: { value: "not-in-url" } });
  expect(start).toBeEnabled(); fireEvent.click(start);
  await waitFor(() => expect(screen.getByText("Live investigation in progress")).toBeInTheDocument());
  expect(window.location.search).not.toContain("not-in-url");
});
