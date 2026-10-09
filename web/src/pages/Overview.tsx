import { Link } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "../components/Card";
import { KpiCard } from "../components/KpiCard";
import { Badge, type BadgeTone } from "../components/Badge";
import { AsyncStatus } from "../components/AsyncStatus";
import { getOverview } from "../api/client";
import { RECOVERY_LATENCY_TARGET_SECONDS } from "../api/types";
import { formatDateTime, formatMetric } from "../lib/format";
import { useAsyncData } from "../lib/useAsyncData";

const SEVERITY_TONE: Record<string, BadgeTone> = {
  critical: "danger",
  high: "danger",
  medium: "warn",
  low: "ok",
};

const CLOUD_STATUS_TONE: Record<string, BadgeTone> = {
  healthy: "ok",
  degraded: "warn",
  down: "danger",
};

export function Overview() {
  const state = useAsyncData(getOverview);

  if (state.status !== "success") {
    return <AsyncStatus state={state} loadingLabel="Loading overview…" />;
  }
  const data = state.data;

  const chartData = data.recoveryLatency.map((point) => ({
    time: new Date(point.timestamp).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }),
    latency: point.latencySeconds,
  }));

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-muted">
          What is happening across your cloud right now, and what we did about it.
        </p>
      </header>

      <section
        aria-label="Key metrics"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {data.kpis.map((kpi) => (
          <KpiCard key={kpi.id} label={kpi.label} value={kpi.value} unit={kpi.unit} />
        ))}
      </section>

      <Card title="Recovery latency — target 60s">
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#DAD9D1" strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#5C675F" />
              <YAxis tick={{ fontSize: 11 }} stroke="#5C675F" unit="s" />
              <Tooltip
                formatter={(value) => [
                  formatMetric(typeof value === "number" ? value : null, "s"),
                  "Recovery time",
                ]}
              />
              <ReferenceLine
                y={RECOVERY_LATENCY_TARGET_SECONDS}
                stroke="#9A5B00"
                strokeDasharray="4 4"
                label={{ value: "60s target", position: "insideTopRight", fill: "#9A5B00", fontSize: 11 }}
              />
              <Line
                type="monotone"
                dataKey="latency"
                stroke="#0B5D5A"
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Incident feed">
          <ul className="flex flex-col gap-3">
            {data.incidents.map((incident) => (
              <li key={incident.id}>
                <Link
                  to={`/incidents/${incident.id}`}
                  className="flex min-h-11 flex-col gap-1 rounded-md border border-border p-3 hover:bg-bg focus-visible:outline-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="tabular text-xs text-muted">{incident.id}</span>
                    <Badge
                      tone={SEVERITY_TONE[incident.severity] ?? "neutral"}
                      label={incident.severity}
                    />
                  </div>
                  <span className="text-sm font-medium">{incident.title}</span>
                  <span className="text-xs text-muted">
                    {incident.resourceId} · opened {formatDateTime(incident.openedAt)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Cloud status">
          <ul className="flex flex-col gap-2">
            {data.cloudStatus.map((entry) => (
              <li
                key={entry.provider}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2.5"
              >
                <span className="text-sm">{entry.label}</span>
                <Badge
                  tone={CLOUD_STATUS_TONE[entry.status] ?? "neutral"}
                  label={entry.status}
                />
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Recent activity">
        <ul className="divide-y divide-border">
          {data.activity.map((entry) => (
            <li key={entry.id} className="flex flex-wrap items-baseline gap-2 py-2.5 text-sm">
              <span className="tabular text-xs text-muted">{formatDateTime(entry.timestamp)}</span>
              <span className="font-medium">{entry.actor}</span>
              <span className="text-muted">{entry.message}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
