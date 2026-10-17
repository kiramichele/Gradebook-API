export function percent(value: number | null | undefined, digits = 1): string {
  return value == null ? "—" : `${value.toFixed(digits)}%`;
}

export function weightShare(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value * 1000) / 10}%`;
}

export function number(value: number | null | undefined, digits = 2): string {
  if (value == null) return "—";
  return String(Math.round(value * 10 ** digits) / 10 ** digits);
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year!, month! - 1, day!).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}
