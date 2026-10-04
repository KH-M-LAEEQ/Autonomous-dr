import { formatMetric } from "../lib/format";

export function KpiCard({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null;
  unit?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="eyebrow">{label}</p>
      <p className="tabular mt-2 text-2xl font-semibold">
        {formatMetric(value, unit ? ` ${unit}` : "")}
      </p>
    </div>
  );
}
