import { useEffect, useMemo, useState } from "react";
import { api, type Investigation } from "../services/api";

export const comparisonHeadline = "A label is not evidence.";
export const comparisonIntro = "Issue Triage turns an issue report into a bounded, reviewable test case. Maintainers inspect the evidence and decide what it means.";

function latest(items: Investigation[]) { return [...items].sort((a, b) => (b.completed_at ?? b.updated_at ?? "").localeCompare(a.completed_at ?? a.updated_at ?? ""))[0]; }
function detailHref(id: string) { return `?id=${encodeURIComponent(id)}`; }

export function CompareApproaches() {
  const [items, setItems] = useState<Investigation[]>([]); const [error, setError] = useState<string>();
  useEffect(() => { api.investigations().then((result) => setItems(result.items)).catch((err: Error) => setError(err.message)); }, []);
  const examples = useMemo(() => ({ confirmed: latest(items.filter((item) => item.classification === "BEHAVIOR_GAP_CONFIRMED")), noGap: latest(items.filter((item) => item.classification === "WONT_REPRO" || item.status === "COMPLETED_NO_GAP")) }), [items]);
  const rows = [
    ["Produces a likely classification or prose summary", "Produces a focused test diff and bounded behavior claim"],
    ["Rationale may be prose-only", "Structured JUnit result, validation checks, and reproducibility manifest"],
    ["May rely on model confidence", "Deterministic validation plus optional human semantic review"],
    ["Negative result can be ambiguous", "Needs information, no-gap, and operational outcomes are kept distinct"],
    ["May suggest a label", "Maintainer reviews evidence and decides intent, priority, and action"],
    ["Action can be automated", "GitHub writes are disabled by default and require explicit human approval"],
  ];
  return <section className="compare-page"><div className="compare-hero"><p className="eyebrow">Evidence-first triage</p><h1>{comparisonHeadline}</h1><p>{comparisonIntro}</p></div><section className="comparison-card"><h2>Generic AI triage versus Issue Triage evidence workflow</h2><div className="comparison-grid" role="table" aria-label="Approach comparison"><div role="row" className="comparison-row comparison-header"><b role="columnheader">Typical AI triage</b><b role="columnheader">Issue Triage evidence workflow</b></div>{rows.map(([generic, evidence]) => <div role="row" className="comparison-row" key={generic}><span role="cell">{generic}</span><span role="cell">{evidence}</span></div>)}</div></section><section className="card comparison-chain"><p className="eyebrow">Deterministic confirmation</p><h2>What actually decides a confirmation</h2><p>Changed focused test → Proof-pattern integrity check → Structured JUnit failure → Clean execution → Confirmation rerun → Behavior gap confirmed</p><a href="?brief=1">Inspect the Evidence Brief and validator</a></section><section className="card"><p className="eyebrow">Human decision remains required</p><h2>What it does not decide</h2><ul><li>Whether an issue is a bug, regression, security issue, or intended behavior.</li><li>Priority.</li><li>Whether to close, label, or comment on GitHub.</li><li>Semantic alignment without human review.</li></ul></section><section className="card"><p className="eyebrow">Persisted evidence</p><h2>See the workflow in practice</h2>{error ? <p className="artifact-unavailable">Representative evidence is unavailable: {error}</p> : <div className="brief-actions">{examples.confirmed ? <a className="button-link button-primary" href={detailHref(examples.confirmed.id)}>See a confirmed evidence case</a> : <span className="metadata">No persisted confirmed case available.</span>}{examples.noGap ? <a className="button-link" href={detailHref(examples.noGap.id)}>See a responsible no-gap outcome</a> : <span className="metadata">No persisted no-gap example available.</span>}<a className="button-link" href="?results=1">See the persisted outcome distribution</a></div>}</section><p className="comparison-safety">Public dashboard views are read-only. The optional live demo is disabled by default. Any GitHub comment requires explicit allowlists, a human-approved exact preview, and revalidation.</p></section>;
}
