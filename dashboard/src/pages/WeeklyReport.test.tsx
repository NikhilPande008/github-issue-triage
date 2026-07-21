import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WeeklyReportPage } from "./WeeklyReport";

it("renders only aggregate weekly pilot report data", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("/me") ? { reviewer: { external_id: "reviewer-a", cohort: "MAINTAINER", posting_approver: false, repositories: ["owner/repo"] }, csrf_token: "csrf", expires_at: "2026-07-30T00:00:00Z" } : { id: "report", report_hash: "hash", generated_at: "2026-07-21T00:00:00Z", report: { report_schema_version: "1.0", repository: "owner/repo", period_start: "2026-07-13T00:00:00Z", period_end: "2026-07-20T00:00:00Z", sample_size: 1, investigation_funnel: { status: { COMPLETED: 1 }, classifications: { NEEDS_INFO: 1 } }, review_funnel: { packets_issued: 1, assessments: 1, work_sessions: 1, consensus: { PENDING_REVIEW: 1 }, reason_tags: {} }, reviewer_effort: { total_estimated_active_seconds: 12, active_seconds: { count: 1, p50: 12, p90: 12 } }, measured_operational_inputs: { tracked_openai_cost_usd_total: 0.1, tracked_openai_cost_per_investigation: { count: 1, p50: 0.1, p90: 0.1 }, codex_invocations: 1, codex_wall_seconds: { count: 1, p50: 2, p90: 2 } }, caveats: ["Estimated review time is idle-capped."] } } })));
  render(<WeeklyReportPage />);
  await waitFor(() => expect(screen.getByRole("heading", { name: "Weekly report" })).toBeInTheDocument());
  expect(screen.getByText(/Measured pilot inputs/)).toBeInTheDocument();
  expect(screen.queryByText("reviewer-a")).not.toBeInTheDocument();
});
