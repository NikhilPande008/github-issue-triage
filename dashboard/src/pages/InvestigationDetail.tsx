import { useEffect, useState } from "react";
import { AttemptCard } from "../components/AttemptCard";
import { EvidenceViewer } from "../components/EvidenceViewer";
import { SummaryCard } from "../components/SummaryCard";
import { Timeline } from "../components/Timeline";
import { StatusBadge } from "../components/StatusBadge";
import { api, type EvidenceArtifact, type InvestigationSummary, type TimelineAttempt } from "../services/api";

export function InvestigationDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [summary, setSummary] = useState<InvestigationSummary>(); const [timeline, setTimeline] = useState<TimelineAttempt[]>([]); const [artifacts, setArtifacts] = useState<EvidenceArtifact[]>([]); const [error, setError] = useState<string>();
  useEffect(() => { Promise.all([api.summary(id), api.timeline(id), api.artifacts(id)]).then(([s, t, a]) => { setSummary(s); setTimeline(t.items); setArtifacts(a.items); }).catch((err: Error) => setError(err.message)); }, [id]);
  if (error) return <main><button onClick={onBack}>Back</button><p className="error">Unable to load investigation: {error}</p></main>;
  if (!summary) return <main>Loading investigation evidence…</main>;
  return <main><button onClick={onBack}>Back to investigations</button><h1>Investigation <code>{id}</code></h1><SummaryCard summary={summary} /><Timeline attempts={timeline} />{timeline.map((attempt) => <AttemptCard key={attempt.attempt_number} attempt={attempt} />)}<EvidenceViewer artifacts={artifacts} /><section className="card"><h2>Classification</h2><p><StatusBadge value={summary.classification} /></p><p><b>assertsFailure:</b> <StatusBadge value={summary.asserts_failure} /></p><p><b>Validation reason:</b> {summary.validation_reason ?? "Not recorded"}</p></section><section className="card"><h2>Cost</h2><p>Input tokens: {summary.input_tokens}</p><p>Cached input tokens: {summary.cached_input_tokens}</p><p>Output tokens: {summary.output_tokens}</p><p>Cache hit: {summary.cache_hit_percent === null ? "Not recorded" : `${summary.cache_hit_percent}%`}</p><p>Cost: ${summary.cost_usd.toFixed(6)}</p><p>LLM latency: {summary.latency_ms} ms</p></section></main>;
}
