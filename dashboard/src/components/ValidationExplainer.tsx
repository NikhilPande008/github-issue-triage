import type { ValidationExplainer as ValidationExplainerData } from "../services/api";

const anchorFor: Record<string, string> = { git_diff: "evidence", structured_test_results_junit: "evidence", reproducibility_manifest: "evidence" };

export function ValidationExplainer({ data, investigationId, compact = false }: { data?: ValidationExplainerData; investigationId: string; compact?: boolean }) {
  if (!data || !Array.isArray(data.checks)) return <section className="card"><h2>Why this failure counts</h2><p className="metadata">Deterministic validation evidence is unavailable.</p></section>;
  const confirmed = data.conclusion === "BEHAVIOR_GAP_CONFIRMED";
  const firstBlocked = data.checks.find((item) => item.status !== "PASS");
  const body = <><div className="validation-explainer-grid">{data.checks.map((item) => <article className={`validation-check validation-${item.status.toLowerCase()}`} key={item.id}><span aria-label={`${item.label}: ${item.status}`}>{item.status === "PASS" ? "✓" : item.status === "FAIL" ? "×" : "—"}</span><div><b>{item.label}</b><p>{item.explanation}</p>{item.artifact_kind && <a href={`?id=${encodeURIComponent(investigationId)}#${anchorFor[item.artifact_kind] ?? "attempts"}`}>Open persisted evidence</a>}</div></article>)}</div><p className="validation-conclusion"><b>{confirmed ? "Behavior gap confirmed" : "No behavior gap established"}</b> — {confirmed ? "Every required deterministic check passed. This confirms the focused test fails against the inspected revision; it does not decide whether the behavior is a bug, regression, or intended." : `${firstBlocked?.label ?? "A required deterministic gate"} is ${firstBlocked?.status.toLowerCase() ?? "unavailable"}; this does not invalidate the issue.`}</p></>;
  return <section className="card validation-explainer" id="validation-explainer"><div className="section-heading"><div><p className="eyebrow">Deterministic validator</p><h2>Why this failure counts</h2></div><span className="metadata">{data.version}</span></div>{compact && !confirmed ? <details><summary>Show deterministic validation checks</summary>{body}</details> : body}</section>;
}
