import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Header } from "./main";

it("provides persistent links to the queue, Evidence Brief, Evidence Results, and comparison", () => {
  render(<Header />);
  expect(screen.getByRole("link", { name: "EvidenceTrail, investigation list" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: "Triage Queue" })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: "Evidence Brief" })).toHaveAttribute("href", "?brief=1");
  expect(screen.getByRole("link", { name: "Evidence Results" })).toHaveAttribute("href", "?results=1");
  expect(screen.getByRole("link", { name: "Why evidence?" })).toHaveAttribute("href", "?compare=1");
  expect(screen.getByRole("link", { name: "Retrospective evaluation" })).toHaveAttribute("href", "?evaluation=1");
});
