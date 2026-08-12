type Tone = "ok" | "warn" | "down" | "idle";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  down: "bg-down",
  idle: "bg-idle",
};

/** A state dot. The only place a status colour touches the DOM directly. */
export function Dot({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={`size-2 shrink-0 rounded-full ${TONE_CLASS[tone]}`}
        aria-hidden="true"
      />
      <span className="sr-only">{label}: </span>
    </span>
  );
}

export type { Tone };
