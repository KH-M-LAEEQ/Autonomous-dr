import { USE_MOCK } from "../api/client";

/** Visible whenever the app is reading from the mock data layer, never silently. */
export function SampleDataBadge() {
  if (!USE_MOCK) return null;
  return (
    <span className="tabular inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium text-muted">
      <span aria-hidden="true">●</span>
      Sample data
    </span>
  );
}
