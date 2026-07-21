import { MaintainerReply, missingInfoFromArtifacts } from "./MaintainerReply";
import type { EvidenceArtifact, Investigation, SemanticReview } from "../services/api";

function detailAnchor(id: string, anchor: string) { return `?id=${encodeURIComponent(id)}#${anchor}`; }
function available(artifacts: EvidenceArtifact[], kind: string) { return artifacts.some((artifact) => artifact.kind === kind && artifact.available); }
function setupCommandIsRecorded(summary: Investigation, artifacts: EvidenceArtifact[]) {
  return /(?:setup command|sandbox_setup_command)/i.test(summary.validation_reason ?? "") || artifacts.some((artifact) => artifact.kind === "reproducibility_manifest" && /(?:setup_command|SANDBOX_SETUP_COMMAND)/.test(artifact.content ?? ""));
}

export function NextActions({ summary, artifacts, semanticReview, compact = false }: { summary: Investigation; artifacts: EvidenceArtifact[]; semanticReview?: SemanticReview; compact?: boolean }) {
  const has = (kind: string) => available(artifacts, kind);
  const evidenceLink = (label: string) => <a href={detailAnchor(summary.id, "evidence")}>{label}</a>;
  const base = <p className="next-action-boundary">This is a review recommendation, not an automated issue decision.</p>;
  const classification = summary.classification;
  const noGap = classification === "WONT_REPRO" || summary.status === "COMPLETED_NO_GAP";
  const incomplete = summary.status === "PENDING" || summary.status === "RUNNING";
  const flaky = summary.reproducibility_status === "NOT_CONFIRMED" || /flaky|inconclusive/i.test(summary.validation_reason ?? "");
  const setup = /setup|dependency|environment/i.test(summary.validation_reason ?? "");

  if (classification === "BEHAVIOR_GAP_CONFIRMED") return <section className={`card next-actions ${compact ? "next-actions-compact" : ""}`}><p className="eyebrow">Maintainer next action</p><h2>Review the focused evidence</h2><ul><li>Review the focused failing test and structured evidence.</li><li>Decide whether the observed behavior is intended, a bug, a feature request, or a priority for this repository.</li></ul><p className="next-action-links">{has("git_diff") && evidenceLink("Open changed test and diff")} {has("structured_test_results_junit") && evidenceLink("Open JUnit evidence")} {semanticReview?.packet_status === "AVAILABLE" && <a href={detailAnchor(summary.id, "semantic-review")}>Open semantic-fidelity review</a>} {has("reproducibility_manifest") && evidenceLink("Open reproducibility manifest")}</p>{base}</section>;

  if (classification === "NEEDS_INFO") return <section className="card next-actions"><p className="eyebrow">Maintainer next action</p><h2>Request the missing reproduction details</h2><p>Request the missing reproduction details before making a behavior decision.</p>{has("extraction_json") ? <><h3>Recorded missing information</h3><ul>{missingInfoFromArtifacts(artifacts).map((item) => <li key={item}>{item}</li>)}</ul><p className="next-action-links">{evidenceLink("Open extraction evidence")}</p></> : <p className="artifact-unavailable"><strong>Extraction evidence unavailable.</strong> No persisted missing-information checklist is available.</p>}<MaintainerReply classification={classification} artifacts={artifacts} embedded />{base}</section>;

  if (classification === "NOT_A_BUG") return <section className="card next-actions"><p className="eyebrow">Maintainer next action</p><h2>Possible non-defect framing — human review required</h2><p>Review the evidence and repository intent before deciding whether this is expected behavior, documentation work, or a defect.</p><p>This is an evidence-only suggestion, not a final disposition.</p>{has("extraction_json") && <p className="next-action-links">{evidenceLink("Open extraction evidence")}</p>}{base}</section>;

  if (noGap) return <section className="card next-actions"><p className="eyebrow">Maintainer next action</p><h2>No behavior gap established</h2><p>Review the unsuccessful reproduction evidence.</p><p>If the report can be narrowed with a minimal example, version, environment, or expected/actual behavior, request that detail and investigate again.</p><p className="next-action-links"><a href={detailAnchor(summary.id, "validation-explainer")}>Open validation reason</a> {has("proof_integrity_report") && evidenceLink("Open proof-integrity report")} {has("extraction_json") && evidenceLink("Open extraction evidence")}</p>{base}</section>;

  return <section className="card next-actions"><p className="eyebrow">Maintainer next action</p><h2>Operationally inconclusive</h2><p>Open setup/terminal evidence before deciding whether another investigation is warranted.</p><p className="next-action-links">{evidenceLink("Open setup and terminal evidence")} {summary.repository && <> <code>triage preflight --repository {summary.repository}</code></>}</p>{setup && setupCommandIsRecorded(summary, artifacts) && <p>Provide the explicit repository setup command recorded in the setup diagnostics before retrying.</p>}{flaky && <p>Review flaky confirmation evidence before considering another investigation.</p>}{incomplete && <p>Wait for the active investigation to finish.</p>}{base}</section>;
}
