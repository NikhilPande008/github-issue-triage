import { useEffect, useMemo, useState } from "react";
import { InvestigationTable } from "../components/InvestigationTable";
import { api, type Investigation } from "../services/api";

const verdictOrder: Record<string, number> = { BEHAVIOR_GAP_CONFIRMED: 0, NEEDS_INFO: 1, WONT_REPRO: 2, NOT_A_BUG: 3 };
export const sortQueue = (items: Investigation[]) => [...items].sort((a, b) => (verdictOrder[a.classification ?? ""] ?? 4) - (verdictOrder[b.classification ?? ""] ?? 4) || (b.completed_at ?? b.updated_at ?? "").localeCompare(a.completed_at ?? a.updated_at ?? ""));

export function Investigations() {
  const [items, setItems] = useState<Investigation[]>([]); const [error, setError] = useState<string>(); const [repository, setRepository] = useState(""); const [loading, setLoading] = useState(true);
  useEffect(() => { setLoading(true); api.investigations().then((result) => setItems(sortQueue(result.items))).catch((err: Error) => setError(err.message)).finally(() => setLoading(false)); }, []);
  const repositories = useMemo(() => [...new Set(items.map((item) => item.repository))].sort((a, b) => a.localeCompare(b)), [items]);
  const visibleItems = repository ? items.filter((item) => item.repository === repository) : items;
  return <section><div className="page-heading"><div><p className="eyebrow">Read-only maintainer inbox</p><h1>Triage queue</h1></div><div className="queue-actions"><a className="button-link" href="?brief=1">Open Evidence Brief</a><a className="button-link" href="?results=1">Open Evidence Results</a>{repositories.length > 1 && <label className="filter-label">Repository <select aria-label="Repository filter" value={repository} onChange={(event) => setRepository(event.target.value)}><option value="">All repositories</option>{repositories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>}</div></div>{loading ? <p role="status">Loading triage queue…</p> : error ? <p className="error">Unable to load investigations: {error}</p> : <InvestigationTable items={visibleItems} filtered={Boolean(repository)} />}</section>;
}
