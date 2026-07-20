import type { Investigation } from "../services/api";
import { StatusBadge } from "./StatusBadge";

export function InvestigationTable({ items, onOpen }: { items: Investigation[]; onOpen: (id: string) => void }) {
  if (!items.length) return <div className="empty-state">No investigations have been run yet.<br /><br />Run: <code>triage investigate &lt;issue_number&gt;</code> to create your first investigation.</div>;
  return <div className="table-wrap"><table><thead><tr><th>Investigation</th><th>Repository</th><th>Issue</th><th>Classification</th><th>assertsFailure</th><th>Attempts</th><th>Started</th><th>Duration</th><th>Cost (USD)</th></tr></thead><tbody>
    {items.map((item) => <tr key={item.id} onClick={() => onOpen(item.id)}><td><code>{item.id}</code></td><td>{item.repository}</td><td>#{item.issue_number}</td><td><StatusBadge value={item.classification} /></td><td><StatusBadge value={item.asserts_failure} /></td><td>{item.attempt_count}</td><td>{formatDate(item.started_at)}</td><td>{formatDuration(item.duration_seconds)}</td><td>${item.cost_usd.toFixed(6)}</td></tr>)}
  </tbody></table></div>;
}

export const formatDate = (value: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";
export const formatDuration = (value: number | null) => value === null ? "Not recorded" : `${value.toFixed(1)}s`;
