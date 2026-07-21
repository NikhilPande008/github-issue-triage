import { useEffect, useState } from "react";
import { StatusBadge } from "../components/StatusBadge";
import { api, type Investigation } from "../services/api";

const pageSize = 100;
const maxRecords = 1000;
const terminalStatuses = new Set(["COMPLETED", "COMPLETED_NO_GAP"]);
export const resultsCaveat = "These are persisted investigation outcomes, not ground-truth accuracy measurements. A behavior gap confirmation is deterministic test evidence; non-confirming outcomes do not decide whether an issue is valid, intended, or a bug.";

export function isTerminalClassified(item: Investigation) { return Boolean(item.classification) && item.status !== "RUNNING"; }
export function outcomeDistribution(items: Investigation[]) {
  const terminal = items.filter(isTerminalClassified);
  const count = (classification: string) => terminal.filter((item) => item.classification === classification).length;
  const categorized = new Set(["BEHAVIOR_GAP_CONFIRMED", "NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG"]);
  return {
    confirmed: count("BEHAVIOR_GAP_CONFIRMED"), needsInfo: count("NEEDS_INFO"), wontRepro: count("WONT_REPRO"), notABug: count("NOT_A_BUG"),
    other: terminal.filter((item) => !categorized.has(item.classification ?? "")).length,
    operationalFailures: items.filter((item) => item.status === "FAILED" && !item.classification).length,
    incomplete: items.filter((item) => !isTerminalClassified(item) && !(item.status === "FAILED" && !item.classification)).length,
  };
}

export function representativeEvidence(items: Investigation[]) {
  const terminal = items.filter(isTerminalClassified);
  const latest = (matches: Investigation[]) => [...matches].sort((a, b) => (b.completed_at ?? b.updated_at ?? "").localeCompare(a.completed_at ?? a.updated_at ?? ""))[0];
  return {
    confirmed: latest(terminal.filter((item) => item.classification === "BEHAVIOR_GAP_CONFIRMED")),
    needsInfo: latest(terminal.filter((item) => item.classification === "NEEDS_INFO")),
    noGap: latest(terminal.filter((item) => item.classification === "WONT_REPRO")) ?? latest(terminal.filter((item) => item.status === "COMPLETED_NO_GAP" && item.classification !== "BEHAVIOR_GAP_CONFIRMED" && item.classification !== "NEEDS_INFO")),
  };
}

function detailHref(id: string) { return `?id=${encodeURIComponent(id)}`; }
function Representative({ title, item }: { title: string; item?: Investigation }) {
  if (!item) return <article className="representative-card unavailable-card"><h3>{title}</h3><p>No persisted example available.</p></article>;
  return <a className="representative-card" href={detailHref(item.id)}><p className="eyebrow">{title}</p><h3>{item.repository} #{item.issue_number}</h3><p className="representative-title">{item.issue_title ?? "Issue title not retained"}</p><StatusBadge value={item.classification} /><p className="representative-reason">{item.validation_reason ?? "No validation reason was retained."}</p><span>Open evidence detail →</span></a>;
}

export function EvidenceResults() {
  const [items, setItems] = useState<Investigation[]>([]); const [total, setTotal] = useState(0); const [error, setError] = useState<string>(); const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const first = await api.investigations(1, undefined, pageSize); const all = [...first.items];
        const limit = Math.min(first.total, maxRecords); const pages = Math.ceil(limit / pageSize);
        for (let page = 2; page <= pages; page += 1) all.push(...(await api.investigations(page, undefined, pageSize)).items);
        if (active) { setItems(all.slice(0, maxRecords)); setTotal(first.total); }
      } catch (err) { if (active) setError((err as Error).message); } finally { if (active) setLoading(false); }
    }
    void load(); return () => { active = false; };
  }, []);
  if (loading) return <section><p role="status">Loading persisted investigation results…</p></section>;
  if (error) return <section className="empty-state"><p className="eyebrow">Evidence Results</p><h1>Evidence Results unavailable</h1><p>Persisted investigations could not be loaded: {error}</p><a className="button-link" href="/">View triage queue</a></section>;
  if (!items.length) return <section className="empty-state"><p className="eyebrow">Evidence Results</p><h1>No persisted investigations yet</h1><p>A live or seeded database is required to show an evidence-results snapshot.</p><a className="button-link" href="/">View triage queue</a></section>;
  const counts = outcomeDistribution(items); const examples = representativeEvidence(items); const included = items.length;
  const cards = [
    ["Behavior gap confirmed", counts.confirmed], ["Needs information", counts.needsInfo], ["No behavior gap established", counts.wontRepro], ["Possible non-defect framing", counts.notABug], ["Operational failures", counts.operationalFailures], ["Incomplete/running", counts.incomplete],
  ] as const;
  return <section className="evidence-results"><div className="results-heading"><div><p className="eyebrow">Read-only evidence snapshot</p><h1>Evidence Results</h1></div><a className="button-link" href="/">View triage queue</a></div><p className="results-caveat">{resultsCaveat}</p><p className="metadata">Showing {included} persisted investigation{included === 1 ? "" : "s"}{total > included ? ` of ${total} total records (safe limit: ${maxRecords}).` : "."}</p>
    <section className="results-grid" aria-label="Outcome distribution">{cards.map(([label, count]) => <article className="result-card" key={label}><strong>{count}</strong><span>{label}</span></article>)}{counts.other > 0 && <article className="result-card"><strong>{counts.other}</strong><span>Other bounded classification</span></article>}</section>
    <section className="why-matters"><h2>Why this matters</h2><ul><li>The system confirms a behavior gap only from structured execution evidence.</li><li>It can abstain when an issue lacks enough evidence.</li><li>Operational failures remain visibly separate from bounded review outcomes.</li></ul></section>
    <section><div className="section-heading"><div><p className="eyebrow">Representative evidence</p><h2>Recorded examples</h2></div></div><div className="representative-grid"><Representative title="Behavior gap confirmed" item={examples.confirmed} /><Representative title="Needs information" item={examples.needsInfo} /><Representative title="No behavior gap established" item={examples.noGap} /></div></section>
  </section>;
}
