/** A measured value that is genuinely absent. Never render 0 for this. */
export function formatMetric(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "no data";
  return `${value}${unit}`;
}

/**
 * A term key missing from a `Decision` option's `terms` dict means that term
 * does not apply to this option — distinct from a present value of 0.
 */
export function formatTerm(
  terms: Partial<Record<string, number>>,
  key: string,
): string {
  if (!(key in terms) || terms[key] === undefined) return "n/a";
  return String(terms[key]);
}

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "no data";
  return `$${value.toFixed(2)}`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatCountdown(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
