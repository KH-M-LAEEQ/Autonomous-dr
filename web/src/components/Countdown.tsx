import { useCountdown } from "../lib/useCountdown";
import { formatCountdown } from "../lib/format";

export function Countdown({ totalSeconds }: { totalSeconds: number }) {
  const { remaining, expired } = useCountdown(totalSeconds);
  return (
    <span
      className={`tabular text-lg font-semibold ${expired ? "text-danger" : "text-text"}`}
      role="timer"
      aria-live="polite"
    >
      {expired ? "Time's up" : formatCountdown(remaining)}
    </span>
  );
}
