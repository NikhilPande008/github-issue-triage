import { useEffect, useState } from "react";
import { CopyButton } from "../components/CopyButton";
import { EvidenceViewer } from "../components/EvidenceViewer";
import { MaintainerReply } from "../components/MaintainerReply";
import { SummaryCard } from "../components/SummaryCard";
import { Timeline } from "../components/Timeline";
import { StatusBadge } from "../components/StatusBadge";
import { ValidationHelp } from "../components/ValidationHelp";
import { api, type EvidenceArtifact, type InvestigationSummary, type TimelineAttempt } from "../services/api";

export function InvestigationDetail({ id }: { id: string }) {
  const [summary, setSummary] = useState<InvestigationSummary>(); const [timeline, setTimeline] = useState<TimelineAttempt[]>([]); const [artifacts, setArtifacts] = useState<EvidenceArtifact[]>([]); const [error, setError] = useState<string>(); const [loadingArtifacts, setLoadingArtifacts] = useState(true);
  useEffect(() => {
    setSummary(undefined); setError(undefined); setArtifacts([]); setLoadingArtifacts(true);
    Promise.all([api.summary(id), api.timeline(id)]).then(([s, t]) => { setSummary(s); setTimeline(t.items); }).catch((err: Error) => setError(err.message));
    api.artifacts(id).then((result) => setArtifacts(result.items)).catch((err: Error) => setError(err.message)).finally(() => setLoadingArtifacts(false));
  }, [id]);
  if (error) return <section><a className="back-link" href="/">← Back to investigations</a><p className="error">Unable to load investigation: {error}</p></section>;
  if (!summary) return <section><p role="status">Loading investigation evidence…</p></section>;
  const issueUrl = `https://github.com/${summary.repository}/issues/${summary.issue_number}`;
  return <section><a className="back-link" href="/">← Back to investigations</a><div className="detail-heading"><div><p className="eyebrow">Investigation evidence</p><h1><a href={issueUrl} target="_blank" rel="noreferrer noopener">{summary.repository} #{summary.issue_number} <span className="external-mark" aria-label="opens GitHub in a new tab">↗</span></a></h1><div className="id-line"><code>{id.slice(0, 8)}</code><CopyButton value={id} label="Copy investigation ID" /></div></div><div className="detail-badges"><StatusBadge value={summary.classification} /><StatusBadge value={summary.status} /><span className="asserts-badge"><span>assertsFailure</span><StatusBadge value={summary.asserts_failure} /></span></div></div><SummaryCard summary={summary} /><Timeline attempts={timeline} /><MaintainerReply classification={summary.classification} artifacts={artifacts} /><EvidenceViewer artifacts={artifacts} loading={loadingArtifacts} /><section className="card"><h2>Validation</h2><p className="validation-line"><b>assertsFailure:</b> <StatusBadge value={summary.asserts_failure} /> <ValidationHelp kind="assertsFailure" /></p><p className="validation-line"><b>Validation reason:</b> <ValidationHelp kind="validation reason" /></p><p className="validation-reason">{summary.validation_reason ?? "—"}</p></section></section>;
}
