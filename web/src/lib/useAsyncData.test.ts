import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAsyncData } from "./useAsyncData";

describe("useAsyncData", () => {
  it("starts in the loading state", () => {
    // A promise that never resolves -- the point is the synchronous initial
    // render, so no later state update should land after this test ends.
    const { result } = renderHook(() => useAsyncData(() => new Promise<number>(() => {})));
    expect(result.current.status).toBe("loading");
  });

  it("resolves to the success state with the fetched data", async () => {
    const { result } = renderHook(() => useAsyncData(() => Promise.resolve("ok")));
    await waitFor(() => expect(result.current).toEqual({ status: "success", data: "ok" }));
  });

  it("resolves to the error state instead of hanging on loading forever when the fetch rejects", async () => {
    const { result } = renderHook(() =>
      useAsyncData(() => Promise.reject(new Error("network down"))),
    );
    await waitFor(() => expect(result.current.status).toBe("error"));
    const state = result.current;
    expect(state.status === "error" && state.error.message).toBe("network down");
  });

  it("wraps a non-Error rejection in an Error", async () => {
    const { result } = renderHook(() => useAsyncData(() => Promise.reject("boom")));
    await waitFor(() => expect(result.current.status).toBe("error"));
    const state = result.current;
    expect(state.status === "error" && state.error).toBeInstanceOf(Error);
  });

  it("re-fetches when a dependency changes", async () => {
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useAsyncData(() => Promise.resolve(id), [id]),
      { initialProps: { id: "a" } },
    );
    await waitFor(() => expect(result.current).toEqual({ status: "success", data: "a" }));

    rerender({ id: "b" });
    await waitFor(() => expect(result.current).toEqual({ status: "success", data: "b" }));
  });
});
