import { useEffect, useState } from "react";

/** Ticks down from `totalSeconds` once per second. Never goes negative. */
export function useCountdown(totalSeconds: number) {
  const [remaining, setRemaining] = useState(totalSeconds);

  useEffect(() => {
    setRemaining(totalSeconds);
  }, [totalSeconds]);

  useEffect(() => {
    if (remaining <= 0) return;
    const timer = setInterval(() => {
      setRemaining((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [remaining]);

  return { remaining, expired: remaining <= 0 };
}
