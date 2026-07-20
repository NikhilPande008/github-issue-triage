import { useMemo, useState } from "react";
import type { EvidenceArtifact } from "../services/api";

const labels: Record<string, string> = { git_diff: "Git Diff", pytest_output: "Pytest Output", terminal_log: "Terminal Log", extraction_json: "Extraction JSON" };

function labelForArtifact(artifact: EvidenceArtifact): string {
  const attempt = artifact.path.match(/attempt_(\d+)/)?.[1];
  const label = labels[artifact.kind] ?? artifact.kind;
  return attempt ? `${label} (Attempt ${attempt})` : label;
}

export function EvidenceViewer({ artifacts }: { artifacts: EvidenceArtifact[] }) {
  const ordered = useMemo(() => [...artifacts].sort((a, b) => labelForArtifact(a).localeCompare(labelForArtifact(b))), [artifacts]);
  const [selected, setSelected] = useState(ordered[0]?.id);
  const artifact = ordered.find((item) => item.id === selected) ?? ordered[0];
  if (!artifact) return <section className="card"><h2>Evidence</h2><p>No artifacts were persisted for this investigation.</p></section>;
  return <section className="card"><h2>Evidence</h2><div className="tabs">{ordered.map((item) => <button className={item.id === artifact.id ? "selected" : ""} key={item.id} onClick={() => setSelected(item.id)}>{labelForArtifact(item)}</button>)}</div>{artifact.available && <p className="metadata">{artifact.size_bytes} bytes · {artifact.modified_at ?? "timestamp unavailable"}</p>}{artifact.available ? <pre>{artifact.content}</pre> : <p className="error">{artifact.error}</p>}</section>;
}
