export function StatusBadge({ value }: { value: string | boolean | null }) {
  const raw = value === true ? "TRUE" : value === false ? "FALSE" : value ?? "UNCLASSIFIED";
  const label = raw === "BEHAVIOR_GAP_CONFIRMED"
    ? "Behavior gap confirmed"
    : raw === "COMPLETED_NO_GAP"
      ? "Evidence review complete"
      : raw;
  return <span className={`badge badge-${String(raw).toLowerCase().replaceAll("_", "-")}`}>{label}</span>;
}
