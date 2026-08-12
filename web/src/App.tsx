import { useEffect, useState } from "react";
import { getHealth, getReady } from "./lib/api";
import { useEventStream } from "./lib/ws";
import type { HealthResponse, ReadyResponse } from "./lib/types";
import { Dot } from "./components/Dot";
import { PipelineStrip } from "./components/PipelineStrip";

/** Bump this as weeks land so the pipeline strip stays truthful. */
const WEEKS_BUILT = 1;
const POLL_MS = 5000;

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const { state: wsState, events, send } = useEventStream();

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const [h, r] = await Promise.all([getHealth(), getReady()]);
        if (cancelled) return;
        setHealth(h);
        setReady(r);
        setApiError(null);
      } catch (error) {
        if (!cancelled) setApiError(error instanceof Error ? error.message : "unknown");
      }
    };

    void poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const dependencies = [
    { name: "API", up: health !== null },
    { name: "Postgres", up: ready?.postgres ?? false },
    { name: "InfluxDB", up: ready?.influxdb ?? false },
    { name: "WebSocket", up: wsState === "open" },
  ];
  const allUp = dependencies.every((d) => d.up);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="border-b border-line pb-6">
        <p className="eyebrow">AutonomousDR · control plane · local</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          Stack check
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          {allUp
            ? "Everything this scaffold depends on is answering. You are set up correctly — go to Week 1's \"Done when\" in the README and tick it off."
            : "Something below is not answering. Start the databases with `make up`, then the API with `make api`. Nothing here needs cloud credentials."}
        </p>
      </header>

      <div className="mt-8 grid gap-8 sm:grid-cols-2">
        <section aria-labelledby="deps-heading">
          <h2 id="deps-heading" className="eyebrow mb-3">
            Dependencies
          </h2>
          <ul className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
            {dependencies.map((dependency) => (
              <li
                key={dependency.name}
                className="flex items-center justify-between px-3 py-2.5 text-sm"
              >
                <span className="flex items-center gap-2">
                  <Dot
                    tone={dependency.up ? "ok" : "down"}
                    label={dependency.up ? "up" : "down"}
                  />
                  {dependency.name}
                </span>
                <span className="tabular text-xs text-muted">
                  {dependency.up ? "up" : "no response"}
                </span>
              </li>
            ))}
          </ul>
          {apiError && (
            <p className="mt-2 text-xs text-down">
              Last API error: {apiError}. Run <span className="tabular">make api</span>.
            </p>
          )}
        </section>

        <section aria-labelledby="impl-heading">
          <h2 id="impl-heading" className="eyebrow mb-3">
            Live implementations
          </h2>
          <dl className="divide-y divide-line overflow-hidden rounded border border-line bg-surface">
            {Object.entries(ready?.config ?? {}).map(([slot, implementation]) => (
              <div
                key={slot}
                className="flex items-center justify-between px-3 py-2.5 text-sm"
              >
                <dt className="text-muted">{slot}</dt>
                <dd className="tabular">{implementation}</dd>
              </div>
            ))}
            {!ready && (
              <p className="px-3 py-2.5 text-sm text-muted">
                Waiting for <span className="tabular">/ready</span>.
              </p>
            )}
          </dl>
          <p className="mt-2 text-xs text-muted">
            Each row is one frozen interface. Changing a value here is an{" "}
            <span className="tabular">.env</span> edit, never a code change.
          </p>
        </section>
      </div>

      <div className="mt-8">
        <PipelineStrip built={WEEKS_BUILT} />
      </div>

      <section className="mt-8" aria-labelledby="events-heading">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="events-heading" className="eyebrow">
            Event stream · {wsState}
          </h2>
          <button
            type="button"
            onClick={() => send(`ping ${new Date().toISOString()}`)}
            disabled={wsState !== "open"}
            className="rounded border border-line bg-surface px-2.5 py-1 text-xs font-medium hover:bg-bg disabled:opacity-50"
          >
            Send test frame
          </button>
        </div>
        <div className="rounded border border-line bg-surface">
          {events.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted">
              No frames yet. Send a test frame to prove the socket round-trips.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {events.map((event, index) => (
                <li key={index} className="tabular px-3 py-2 text-xs">
                  <span className="text-muted">{event.type}</span>{" "}
                  {JSON.stringify(event.payload)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <footer className="mt-10 border-t border-line pt-4 text-xs text-muted">
        Replace this page in Week 3 — FRONTEND owns the real dashboard shell.
        {health && (
          <span className="tabular">
            {" "}
            · api {health.version} · env {health.env}
          </span>
        )}
      </footer>
    </div>
  );
}
