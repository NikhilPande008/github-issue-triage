import { useMemo, useState } from "react";
import type { EvidenceArtifact } from "../services/api";
import { CopyButton } from "./CopyButton";
import { formatBytes, formatDate } from "./format";

const labels: Record<string, string> = { git_diff: "Git Diff", pytest_output: "Pytest Output", vitest_output: "Vitest Output", terminal_log: "Terminal Log", extraction_json: "Extraction JSON", structured_test_results_junit: "Structured test results (JUnit XML)", reproducibility_manifest: "Reproducibility manifest", proof_integrity_report: "Proof-integrity report", focused_test_selection: "Focused-test selection" };

function labelForArtifact(artifact: EvidenceArtifact): string {
  const attempt = artifact.path.match(/attempt_(\d+)/)?.[1];
  const label = labels[artifact.kind] ?? artifact.kind;
  return attempt ? `${label} (Attempt ${attempt})` : label;
}

function DiffContent({ content }: { content: string }) {
  return <>{content.split("\n").map((line, index) => <span key={index} className={line.startsWith("+") && !line.startsWith("+++") ? "diff-add" : line.startsWith("-") && !line.startsWith("---") ? "diff-remove" : line.startsWith("@@") ? "diff-hunk" : line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("+++") || line.startsWith("---") ? "diff-header" : undefined}>{line}{"\n"}</span>)}</>;
}

function PytestContent({ content }: { content: string }) {
  return <>{content.split("\n").map((line, index) => <span key={index} className={line.startsWith("FAILED ") ? "pytest-failed" : /\b\d+ failed(?:,| in )/.test(line) ? "pytest-summary" : undefined}>{line}{"\n"}</span>)}</>;
}

function JsonContent({ content }: { content: string }) {
  let formatted = content;
  try { formatted = JSON.stringify(JSON.parse(content), null, 2); } catch { /* preserve stored evidence */ }
  return <>{formatted.split("\n").map((line, index) => {
    const tokens = [...line.matchAll(/"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\b\d+(?:\.\d+)?\b/g)];
    let cursor = 0;
    return <span key={index}>{tokens.map((match, tokenIndex) => {
      const token = match[0]; const start = match.index ?? 0; const suffix = line.slice(start + token.length).trimStart();
      const className = token.startsWith('"') ? (suffix.startsWith(":") ? "json-key" : "json-string") : /^(true|false|null)$/.test(token) ? "json-literal" : "json-number";
      const before = line.slice(cursor, start); cursor = start + token.length;
      return <span key={tokenIndex}>{before}<span className={className}>{token}</span></span>;
    })}{line.slice(cursor)}{"\n"}</span>;
  })}</>;
}

function ArtifactContent({ artifact }: { artifact: EvidenceArtifact }) {
  const content = artifact.content ?? "";
  if (artifact.kind === "git_diff") return <DiffContent content={content} />;
  if (artifact.kind === "pytest_output") return <PytestContent content={content} />;
  if (artifact.kind === "extraction_json") return <JsonContent content={content} />;
  return content;
}

function FocusedSelectionSummary({ artifact }: { artifact: EvidenceArtifact }) {
  if (artifact.kind !== "focused_test_selection" || !artifact.available || !artifact.content) return null;
  try {
    const selection = JSON.parse(artifact.content) as { precision?: string; targets?: unknown };
    const targets = Array.isArray(selection.targets) ? selection.targets.filter((target): target is string => typeof target === "string") : [];
    return <p className="metadata"><b>Selection precision:</b> {selection.precision ?? "UNAVAILABLE"}{targets.length ? <> · <b>Selected target{targets.length === 1 ? "" : "s"}:</b> {targets.join(", ")}</> : null}</p>;
  } catch {
    return <p className="metadata">Focused-test selection artifact is not valid JSON.</p>;
  }
}

export function EvidenceViewer({ artifacts, loading = false }: { artifacts: EvidenceArtifact[]; loading?: boolean }) {
  const ordered = useMemo(() => [...artifacts].sort((a, b) => labelForArtifact(a).localeCompare(labelForArtifact(b))), [artifacts]);
  const [selected, setSelected] = useState(ordered[0]?.id);
  const artifact = ordered.find((item) => item.id === selected) ?? ordered[0];
  if (loading) return <section className="card"><h2>Evidence</h2><p className="metadata" role="status">Loading persisted artifacts…</p></section>;
  if (!artifact) return <section className="card"><h2>Evidence</h2><p>No artifacts were persisted for this investigation.</p></section>;
  return <section className="card" id="evidence"><div className="section-heading"><h2>Evidence</h2>{artifact.available && <CopyButton value={artifact.content ?? ""} label={`Copy ${labelForArtifact(artifact)}`} />}</div><div className="tabs" role="tablist" aria-label="Evidence artifacts">{ordered.map((item) => <button className={item.id === artifact.id ? "selected" : ""} key={item.id} onClick={() => setSelected(item.id)} role="tab" aria-selected={item.id === artifact.id}>{labelForArtifact(item)}</button>)}</div>{artifact.available ? <><p className="metadata">{formatBytes(artifact.size_bytes)} · {artifact.modified_at ? formatDate(artifact.modified_at) : "timestamp unavailable"}</p><FocusedSelectionSummary artifact={artifact} /><pre className={`evidence-code evidence-${artifact.kind}`}><code><ArtifactContent artifact={artifact} /></code></pre></> : <div className="artifact-unavailable"><strong>Artifact unavailable</strong><p>{artifact.error ?? "This persisted artifact could not be read."}</p></div>}</section>;
}
