export const formatDate = (value: string | null) => {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

export const formatDuration = (value: number | null) => value === null ? "—" : `${value.toFixed(1)}s`;
export const formatUsd = (value: number | null) => {
  if (value === null) return "—";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
};
export const formatBytes = (value: number | null) => {
  if (value === null) return "size unavailable";
  if (value < 1024) return `${value} B`;
  return `${(value / 1024).toFixed(1)} KB`;
};
