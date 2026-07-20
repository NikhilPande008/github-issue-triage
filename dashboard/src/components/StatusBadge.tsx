export function StatusBadge({ value }: { value: string | boolean | null }) {
  const label = value === true ? "TRUE" : value === false ? "FALSE" : value ?? "UNCLASSIFIED";
  return <span className={`badge badge-${String(label).toLowerCase().replaceAll("_", "-")}`}>{label}</span>;
}
