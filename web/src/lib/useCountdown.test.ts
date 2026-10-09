import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCountdown } from "./useCountdown";

describe("useCountdown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts at the given number of seconds", () => {
    const { result } = renderHook(() => useCountdown(10));
    expect(result.current.remaining).toBe(10);
    expect(result.current.expired).toBe(false);
  });

  it("ticks down by one second at a time", () => {
    const { result } = renderHook(() => useCountdown(10));
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current.remaining).toBe(7);
  });

  it("stops at zero and reports expired instead of going negative", () => {
    const { result } = renderHook(() => useCountdown(2));
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(result.current.remaining).toBe(0);
    expect(result.current.expired).toBe(true);
  });
});
