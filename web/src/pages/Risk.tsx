import { Card } from "../components/Card";
import { Badge, type BadgeTone } from "../components/Badge";
import { AsyncStatus } from "../components/AsyncStatus";
import { getRegionalRisk } from "../api/client";
import type { RegionRisk } from "../api/types";
import { riskLevelFor } from "../api/types";
import { formatDateTime } from "../lib/format";
import { useAsyncData } from "../lib/useAsyncData";

const LEVEL_TONE: Record<string, BadgeTone> = {
  low: "ok",
  elevated: "warn",
  high: "danger",
};

const LEVEL_LABEL: Record<string, string> = {
  low: "Low",
  elevated: "Elevated",
  high: "High",
};

function groupByProvider(regions: RegionRisk[]): Map<string, RegionRisk[]> {
  const groups = new Map<string, RegionRisk[]>();
  for (const region of regions) {
    const list = groups.get(region.provider) ?? [];
    list.push(region);
    groups.set(region.provider, list);
  }
  return groups;
}

function formulaFor(region: RegionRisk): string {
  const { incidentDensity, advisorySeverity, geopoliticalFlag, weights } = region.breakdown;
  return (
    `${weights.incidentDensity.toFixed(2)}×${incidentDensity.toFixed(2)} (incident density) + ` +
    `${weights.advisorySeverity.toFixed(2)}×${advisorySeverity.toFixed(2)} (advisory severity) + ` +
    `${weights.geopoliticalFlag.toFixed(2)}×${geopoliticalFlag.toFixed(2)} (geopolitical flag) = ${region.score.toFixed(2)}`
  );
}

export function Risk() {
  const state = useAsyncData(getRegionalRisk);

  if (state.status !== "success") {
    return <AsyncStatus state={state} loadingLabel="Loading regional risk…" />;
  }
  const data = state.data;

  const groups = groupByProvider(data.regions);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Regional risk</h1>
        <p className="mt-1 text-sm text-muted">
          Risk score = 0.30 × incident density + 0.40 × advisory severity + 0.30 × geopolitical flag.
          Levels: ● Low below 0.33, ▲ Elevated 0.33–0.66, ■ High at or above 0.66.
        </p>
      </header>

      {Array.from(groups.entries()).map(([provider, regions]) => (
        <Card key={provider} title={provider.toUpperCase()}>
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {regions.map((region) => {
              const level = riskLevelFor(region.score);
              return (
                <li key={region.id} className="rounded-md border border-border p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{region.name}</span>
                    <Badge tone={LEVEL_TONE[level]} label={LEVEL_LABEL[level]} />
                  </div>
                  <p className="tabular mt-1 text-2xl font-semibold">{region.score.toFixed(2)}</p>
                  <p className="tabular mt-2 text-xs text-muted">{formulaFor(region)}</p>

                  {region.signals.length > 0 ? (
                    <ul className="mt-3 flex flex-col gap-1.5 border-t border-border pt-3">
                      {region.signals.map((signal) => (
                        <li key={signal.id} className="text-xs">
                          <a
                            href={signal.source.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-accent underline underline-offset-2"
                          >
                            {signal.label}
                          </a>
                          <span className="tabular text-muted"> · {signal.source.label} · {formatDateTime(signal.observedAt)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-3 border-t border-border pt-3 text-xs text-muted">No data</p>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      ))}

      <Card title="Tenant risk-weight policy">
        <p className="text-sm">
          Geopolitical weight is capped by your tenant's policy limit. Current weight:{" "}
          <span className="tabular font-medium">{data.weightPolicy.current.toFixed(2)}</span>
        </p>
        <p className="tabular mt-1 text-xs text-muted">
          Allowed range: min {data.weightPolicy.min.toFixed(2)} · max {data.weightPolicy.max.toFixed(2)} ·
          default {data.weightPolicy.default.toFixed(2)}
        </p>
      </Card>
    </div>
  );
}
