export type BadgeTone = "ok" | "warn" | "danger" | "neutral";

const TONE_STYLE: Record<BadgeTone, string> = {
  ok: "bg-ok/10 text-ok",
  warn: "bg-warn/10 text-warn",
  danger: "bg-danger/10 text-danger",
  neutral: "bg-border/40 text-muted",
};

const TONE_SYMBOL: Record<BadgeTone, string> = {
  ok: "●",
  warn: "▲",
  danger: "■",
  neutral: "○",
};

/**
 * Colour is never the only signal — every badge pairs its tone with a symbol
 * and a word, so the meaning survives for colour-blind users and in print.
 */
export function Badge({
  tone,
  label,
  symbol,
}: {
  tone: BadgeTone;
  label: string;
  symbol?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${TONE_STYLE[tone]}`}
    >
      <span aria-hidden="true">{symbol ?? TONE_SYMBOL[tone]}</span>
      <span>{label}</span>
    </span>
  );
}
