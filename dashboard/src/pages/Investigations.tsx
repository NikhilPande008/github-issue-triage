import { useEffect, useState } from "react";
import { InvestigationTable } from "../components/InvestigationTable";
import { api, type Classification, type Investigation } from "../services/api";

const verdictOrder: Record<string, number> = { BEHAVIOR_GAP_CONFIRMED: 0, NEEDS_INFO: 1, WONT_REPRO: 2, NOT_A_BUG: 3 };
export const sortQueue = (items: Investigation[]) => [...items].sort((a, b) => (verdictOrder[a.classification ?? ""] ?? 4) - (verdictOrder[b.classification ?? ""] ?? 4) || (b.completed_at ?? b.updated_at ?? "").localeCompare(a.completed_at ?? a.updated_at ?? ""));

export function Investigations() {
  const [items, setItems] = useState<Investigation[]>([]); const [error, setError] = useState<string>(); const [classification, setClassification] = useState<Classification | undefined>(); const [loading, setLoading] = useState(true);
  useEffect(() => { setLoading(true); api.investigations(1, classification).then((result) => setItems(sortQueue(result.items))).catch((err: Error) => setError(err.message)).finally(() => setLoading(false)); }, [classification]);
  return <section><div className="page-heading"><div><p className="eyebrow">Read-only maintainer inbox</p><h1>Triage queue</h1></div><div className="queue-actions"><a className="button-link" href="?brief=1">Open Evidence Brief</a><a className="button-link" href="?results=1">Open Evidence Results</a><label className="filter-label">Classification <select aria-label="Classification filter" value={classification ?? ""} onChange={(event) => setClassification((event.target.value || undefined) as Classification | undefined)}><option value="">All classifications</option><option value="BEHAVIOR_GAP_CONFIRMED">Behavior gap confirmed</option>{["NEEDS_INFO", "WONT_REPRO", "NOT_A_BUG"].map((value) => <option key={value}>{value}</option>)}</select></label></div></div>{loading ? <p role="status">Loading triage queue…</p> : error ? <p className="error">Unable to load investigations: {error}</p> : <InvestigationTable items={items} filtered={Boolean(classification)} />}</section>;
}
