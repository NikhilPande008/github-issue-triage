import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Investigations } from "./Investigations";

it("renders API errors without crashing", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: "Database unavailable" }) }));
  render(<Investigations onOpen={vi.fn()} />);
  await waitFor(() => expect(screen.getByText(/Database unavailable/)).toBeInTheDocument());
});
