import type { InvestigationSummary } from "../services/api";
import type { ReactNode } from "react";
import { formatDuration, formatUsd } from "./format";

function unavailable(label: string, detail: string) {
  return <span className="unavailable" title={detail} aria-label={`${label}: unavailable. ${detail}`}>—</span>;
}

export function SummaryCard({ summary }: { summary: InvestigationSummary }) {
  const fields: [string, ReactNode][] = [
    ["Total attempts", summary.attempt_count],
    ["Total duration", summary.total_duration_seconds === null ? unavailable("Total duration", "Duration was not recorded for this investigation.") : formatDuration(summary.total_duration_seconds)],
    ["Tracked LLM API cost", summary.tracked_llm_api_cost_usd === null ? unavailable("Tracked LLM API cost", summary.tracked_llm_api_explanation) : formatUsd(summary.tracked_llm_api_cost_usd)],
    ["Cached tokens", summary.cached_input_tokens === null ? unavailable("Cached tokens", summary.tracked_llm_api_explanation) : summary.cached_input_tokens],
    ["Total tokens", summary.total_tokens === null ? unavailable("Total tokens", summary.tracked_llm_api_explanation) : summary.total_tokens],
    ["Cache hit", summary.cache_hit_percent === null ? unavailable("Cache hit", "Cache usage was not recorded for this investigation.") : `${summary.cache_hit_percent}%`],
    ["Tracked LLM API latency", summary.latency_ms === null ? unavailable("Tracked LLM API latency", summary.tracked_llm_api_explanation) : `${(summary.latency_ms / 1000).toFixed(1)}s`],
  ];
  return <section className="card"><h2>Metrics</h2><dl className="summary-grid">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><p className="metadata">{summary.tracked_llm_api_explanation}</p></section>;
}
