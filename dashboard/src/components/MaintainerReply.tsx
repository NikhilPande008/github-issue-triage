import { CopyButton } from "./CopyButton";
import type { EvidenceArtifact } from "../services/api";

export const FALLBACK_MISSING_INFO = [
  "the affected package and version",
  "your Python version and operating system",
  "a minimal reproducible example",
  "the complete traceback, or the observed and expected behavior",
];

export function normalizeMissingInfo(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  return value.flatMap((item) => {
    if (typeof item !== "string") return [];
    const normalized = item.replace(/^\s*[-*•]\s+/, "").replace(/\s+/g, " ").trim();
    if (!normalized || seen.has(normalized.toLocaleLowerCase())) return [];
    seen.add(normalized.toLocaleLowerCase());
    return [normalized];
  });
}

export function missingInfoFromArtifacts(artifacts: EvidenceArtifact[]): string[] {
  const extraction = artifacts.find((artifact) => artifact.kind === "extraction_json" && artifact.available && artifact.content);
  if (!extraction?.content) return [];
  try {
    return normalizeMissingInfo((JSON.parse(extraction.content) as { missing_info?: unknown }).missing_info);
  } catch {
    return [];
  }
}

export function buildMaintainerReply(missingInfo: string[]): string {
  const items = missingInfo.length ? missingInfo : FALLBACK_MISSING_INFO;
  return `Thanks for the report. To investigate this, please provide:\n${items.map((item) => `- ${item}`).join("\n")}`;
}

export function MaintainerReply({ classification, artifacts, embedded = false }: { classification: string | null; artifacts: EvidenceArtifact[]; embedded?: boolean }) {
  if (classification !== "NEEDS_INFO") return null;
  const reply = buildMaintainerReply(missingInfoFromArtifacts(artifacts));
  return <section className={embedded ? "maintainer-reply-card" : "card maintainer-reply-card"}>
    <div className="section-heading">
      <div>
        <h3>Copyable reply preview</h3>
        <p className="preview-note">Preview only — not posted to GitHub.</p>
      </div>
      <CopyButton value={reply} label="Copy maintainer-ready reply" />
    </div>
    <pre className="maintainer-reply">{reply}</pre>
  </section>;
}
