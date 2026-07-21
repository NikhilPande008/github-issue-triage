export function StatusBadge({ value }: { value: string | boolean | null }) {
  const raw = value === true ? "TRUE" : value === false ? "FALSE" : value ?? "UNCLASSIFIED";
  const labels: Record<string, string> = {
    BEHAVIOR_GAP_CONFIRMED: "Behavior gap confirmed",
    NEEDS_INFO: "Needs information",
    WONT_REPRO: "No behavior gap established",
    NOT_A_BUG: "Possible non-defect framing",
    COMPLETED: "Evidence review complete",
    COMPLETED_NO_GAP: "Evidence review complete",
    FAILED: "Operationally inconclusive",
    PENDING: "Pending investigation",
    RUNNING: "Investigation in progress",
    FLAKY_OR_INCONCLUSIVE: "Flaky or inconclusive",
    UNCLASSIFIED: "No classification recorded",
  };
  const label = labels[raw] ?? raw;
  return <span className={`badge badge-${String(raw).toLowerCase().replaceAll("_", "-")}`}>{label}</span>;
}
