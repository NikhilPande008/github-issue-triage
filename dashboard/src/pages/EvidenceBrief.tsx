import { useEffect, useMemo, useState } from "react";
import { CopyButton } from "../components/CopyButton";
import { StatusBadge } from "../components/StatusBadge";
import { ValidationExplainer } from "../components/ValidationExplainer";
import { NextActions } from "../components/NextActions";
import { api, type EvidenceArtifact, type Investigation, type SemanticReview, type ValidationExplainer as ValidationExplainerData } from "../services/api";

export const boundedCaveat = "A focused test confirms the reported behavior is absent in the inspected revision. This is not a decision that the report is a bug, regression, or intended behavior.";

function artifact(artifacts: EvidenceArtifact[], kind: string) { return artifacts.find((item) => item.kind === kind); }
function diffPath(content: string | null | undefined) {
  for (const line of content?.split("\n") ?? []) {
    const path = line.match(/^\+\+\+ b\/(.+)/)?.[1];
    if (path && (/(?:^|\/)test[^/]*\//i.test(path) || /test_/i.test(path))) return path;
  }
  return undefined;
}
function DiffExcerpt({ content }: { content: string }) {
  return <pre className="evidence-code brief-code"><code>{content.split("\n").slice(0, 70).map((line, index) => <span key={index} className={line.startsWith("+") && !line.startsWith("+++") ? "diff-add" : line.startsWith("-") && !line.startsWith("---") ? "diff-remove" : line.startsWith("@@") ? "diff-hunk" : line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("+++") || line.startsWith("---") ? "diff-header" : undefined}>{line}{"\n"}</span>)}</code></pre>;
}

function detailHref(id: string) { return `?id=${encodeURIComponent(id)}`; }

export function EvidenceBrief() {
  const [selected, setSelected] = useState<Investigation>();
  const [artifacts, setArtifacts] = useState<EvidenceArtifact[]>([]);
  const [validationExplainer, setValidationExplainer] = useState<ValidationExplainerData>();
  const [semanticReview, setSemanticReview] = useState<SemanticReview>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true); setError(undefined);
    api.investigations(1, "BEHAVIOR_GAP_CONFIRMED").then(({ items }) => {
      const newest = [...items].sort((a, b) => (b.completed_at ?? b.updated_at ?? "").localeCompare(a.completed_at ?? a.updated_at ?? ""))[0];
      setSelected(newest);
      return newest ? Promise.all([api.artifacts(newest.id).then(({ items: evidence }) => setArtifacts(evidence)), api.validationExplainer(newest.id).then(setValidationExplainer), api.semanticReview(newest.id).then(setSemanticReview).catch(() => undefined)]) : undefined;
    }).catch((err: Error) => setError(err.message)).finally(() => setLoading(false));
  }, []);
  const evidence = useMemo(() => ({ diff: artifact(artifacts, "git_diff"), junit: artifact(artifacts, "structured_test_results_junit") }), [artifacts]);
  if (loading) return <section><p role="status">Loading latest confirmed evidence brief…</p></section>;
  if (error) return <section className="empty-state"><h1>Evidence Brief unavailable</h1><p>Recorded investigations could not be loaded: {error}</p><a className="button-link" href="/">View triage queue</a></section>;
  if (!selected) return <section className="empty-state"><p className="eyebrow">Evidence Brief</p><h1>No confirmed investigation is available</h1><p>A brief is shown only when recorded investigation data has a Behavior gap confirmed outcome.</p><a className="button-link" href="/">View triage queue</a></section>;
  const issueUrl = `https://github.com/${selected.repository}/issues/${selected.issue_number}`;
  const path = diffPath(evidence.diff?.content);
  const unavailable = (item: EvidenceArtifact | undefined, label: string) => <p className="artifact-unavailable"><strong>{label} unavailable.</strong> {item?.error ?? "No persisted artifact is available for this investigation."}</p>;
  return <section className="evidence-brief">
    <a className="back-link" href="/">← Back to triage queue</a>
    <div className="brief-hero"><div><p className="eyebrow">Submission-ready evidence brief</p><h1>{selected.issue_title ?? `${selected.repository} #${selected.issue_number}`}</h1><p className="brief-issue"><a href={issueUrl} target="_blank" rel="noreferrer noopener">{selected.repository} #{selected.issue_number} ↗</a></p><div className="id-line"><code>{selected.id.slice(0, 8)}</code><CopyButton value={selected.id} label="Copy investigation ID" /></div></div><StatusBadge value="BEHAVIOR_GAP_CONFIRMED" /></div>
    <p className="brief-caveat">{boundedCaveat}</p>
    <ValidationExplainer data={validationExplainer} investigationId={selected.id} />
    <NextActions summary={selected} artifacts={artifacts} semanticReview={semanticReview} compact />
    <section className="brief-card"><h2>Evidence path</h2><ol className="evidence-path"><li><b>Report</b><span>{selected.issue_title ?? "The recorded GitHub issue report."}</span></li><li><b>Focused test</b><span>{path ? `Changed test recorded at ${path}.` : "No changed test path is available in the persisted diff."}</span></li><li><b>Structured test result</b><span>{evidence.junit?.available ? "Recorded JUnit XML contains the validator input." : "Structured JUnit XML is unavailable."}</span></li><li><b>Decision</b><span>{selected.validation_reason ?? "No deterministic validation reason was retained."}</span></li></ol></section>
    <section className="brief-card"><div className="section-heading"><div><p className="eyebrow">Focused test change</p><h2>{path ?? "Changed test path unavailable"}</h2></div></div>{evidence.diff?.available && evidence.diff.content ? <DiffExcerpt content={evidence.diff.content} /> : unavailable(evidence.diff, "Git diff")}</section>
    <section className="brief-card"><div className="section-heading"><div><p className="eyebrow">Structured proof</p><h2>JUnit XML <span className="metadata">— authoritative validator input</span></h2></div><a className="button-link" href={detailHref(selected.id)}>Open full artifact</a></div>{evidence.junit?.available && evidence.junit.content ? <pre className="evidence-code brief-code"><code>{evidence.junit.content.slice(0, 5000)}</code></pre> : unavailable(evidence.junit, "JUnit XML")}</section>
    <section className="brief-card decision-card"><p className="eyebrow">Bounded decision</p><h2>Behavior gap confirmed</h2><p><b>assertsFailure=true</b></p><p>{selected.validation_reason ?? "—"}</p><p>{boundedCaveat}</p><div className="brief-actions"><a className="button-link" href={detailHref(selected.id)}>Open complete evidence trail</a><a className="button-link" href="/">View triage queue</a></div></section>
    <footer className="brief-provenance"><a href="?results=1">Evidence Results</a><span>Runner: {selected.test_runner ?? "—"}</span><span>Reproducibility: {selected.reproducibility_status ?? "—"}</span><span title={selected.tracked_llm_api_explanation}>Tracked OpenAI cost: {selected.tracked_llm_api_cost_usd == null ? "—" : `$${selected.tracked_llm_api_cost_usd.toFixed(4)}`}</span><span title={selected.tracked_llm_api_explanation}>Tracked OpenAI latency: {selected.tracked_llm_api_latency_ms == null ? "—" : `${selected.tracked_llm_api_latency_ms}ms`}</span><span title="Codex execution is excluded from tracked OpenAI API cost and latency.">Codex excluded from tracked API metrics</span></footer>
  </section>;
}
