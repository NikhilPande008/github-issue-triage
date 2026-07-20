import type { InvestigationSummary } from "../services/api";
import type { ReactNode } from "react";
import { formatDuration } from "./InvestigationTable";
import { StatusBadge } from "./StatusBadge";

export function SummaryCard({ summary }: { summary: InvestigationSummary }) {
  const fields: [string, ReactNode][] = [
    ["Repository", summary.repository], ["Issue", `#${summary.issue_number}`], ["Status", <StatusBadge value={summary.status} />],
    ["Classification", <StatusBadge value={summary.classification} />], ["assertsFailure", <StatusBadge value={summary.asserts_failure} />], ["Total attempts", summary.attempt_count],
    ["Total duration", formatDuration(summary.total_duration_seconds)], ["GPT cost", `$${summary.cost_usd.toFixed(6)}`], ["Cached tokens", summary.cached_input_tokens], ["Total tokens", summary.total_tokens],
  ];
  return <section className="card"><h2>Summary</h2><dl className="summary-grid">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section>;
}
