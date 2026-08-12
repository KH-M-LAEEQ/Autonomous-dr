import { Dot, type Tone } from "./Dot";

/**
 * The spine, as a strip.
 *
 * Phase 1 of the build plan is "one path through every layer". This strip is that
 * path, and each stage is lit only when the stage actually exists — so the page is
 * honest about a half-built system instead of pretending. Update `built` as weeks
 * land; the last stage to light up is the one to work on next.
 */
const STAGES = [
  { week: 3, name: "collect", detail: "Celery beat → InfluxDB" },
  { week: 4, name: "detect", detail: "AnomalyDetector" },
  { week: 5, name: "decide", detail: "U(c, l, m)" },
  { week: 5, name: "cost gate", detail: "budget refusal" },
  { week: 5, name: "vote", detail: "ConsensusStrategy" },
  { week: 5, name: "act", detail: "ActionExecutor" },
  { week: 4, name: "audit", detail: "hash chain" },
] as const;

export function PipelineStrip({ built }: { built: number }) {
  return (
    <section aria-labelledby="spine-heading">
      <h2 id="spine-heading" className="eyebrow mb-3">
        Recovery path · lit stages are implemented
      </h2>
      <ol className="flex flex-wrap items-stretch gap-px overflow-hidden rounded border border-line bg-line">
        {STAGES.map((stage) => {
          const live = stage.week <= built;
          const tone: Tone = live ? "ok" : "idle";
          return (
            <li
              key={stage.name}
              className={`flex-1 basis-32 bg-surface px-3 py-2.5 ${live ? "" : "opacity-55"}`}
            >
              <div className="flex items-center gap-2">
                <Dot tone={tone} label={live ? "implemented" : "not built yet"} />
                <span className="text-sm font-medium">{stage.name}</span>
              </div>
              <p className="tabular mt-1 text-[0.6875rem] text-muted">
                wk{stage.week} · {stage.detail}
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
