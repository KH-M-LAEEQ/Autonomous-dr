import { Card } from "../components/Card";
import { Badge, type BadgeTone } from "../components/Badge";
import { AsyncStatus } from "../components/AsyncStatus";
import { getTopology } from "../api/client";
import type { TopologyService } from "../api/types";
import { useAsyncData } from "../lib/useAsyncData";

const STATUS_TONE: Record<TopologyService["status"], BadgeTone> = {
  healthy: "ok",
  degraded: "warn",
  failed: "danger",
};

export function Topology() {
  const state = useAsyncData(getTopology);

  if (state.status !== "success") {
    return <AsyncStatus state={state} loadingLabel="Loading topology…" />;
  }
  const data = state.data;

  const serviceById = new Map(data.services.map((service) => [service.id, service]));
  const predicted = serviceById.get(data.predictedNextAtRisk.serviceId);
  const blastPercent = Math.round((data.blastRadius.affected / data.blastRadius.total) * 100);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Topology</h1>
        <p className="mt-1 text-sm text-muted">
          How your services depend on each other, and what the failure could spread to.
        </p>
      </header>

      <Card title="Services">
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.services.map((service) => {
            const isFailed = service.id === data.failedServiceId;
            return (
              <li
                key={service.id}
                className={`rounded-md border p-3 ${
                  isFailed ? "border-danger bg-danger/5" : "border-border"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{service.name}</span>
                  <Badge tone={STATUS_TONE[service.status]} label={service.status} />
                </div>
                <p className="tabular mt-1 text-xs text-muted">
                  {service.id} · {service.provider.toUpperCase()}
                </p>
              </li>
            );
          })}
        </ul>
      </Card>

      <Card title="Dependencies">
        <ul className="flex flex-col gap-1.5 text-sm">
          {data.edges.map((edge) => {
            const from = serviceById.get(edge.from);
            const to = serviceById.get(edge.to);
            return (
              <li key={`${edge.from}-${edge.to}`} className="tabular text-xs text-muted">
                {from?.name ?? edge.from} <span aria-hidden="true">→</span> {to?.name ?? edge.to}
              </li>
            );
          })}
        </ul>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Blast radius">
          <p className="tabular text-2xl font-semibold">
            {data.blastRadius.affected} of {data.blastRadius.total} services affected
          </p>
          <div
            role="progressbar"
            aria-valuenow={blastPercent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Blast radius"
            className="mt-3 h-2 w-full overflow-hidden rounded-full bg-border"
          >
            <div className="h-full rounded-full bg-danger" style={{ width: `${blastPercent}%` }} />
          </div>
        </Card>

        <Card title="Predicted next at risk">
          {predicted && (
            <>
              <p className="text-sm font-medium">{predicted.name}</p>
              <p className="tabular mt-1 text-2xl font-semibold">
                {Math.round(data.predictedNextAtRisk.probability * 100)}% probability
              </p>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
