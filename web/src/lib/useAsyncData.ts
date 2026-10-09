import { useEffect, useState } from "react";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; error: Error }
  | { status: "success"; data: T };

/**
 * Every page in src/pages fetches one thing on mount (or when an id in the
 * URL changes) and needs the same three states: loading, error, success.
 * Before this hook each page had its own useEffect/useState copy with no
 * `.catch` at all -- a rejected fetch left the page stuck on "Loading…"
 * forever instead of showing an error. This is the one place that fixes it.
 *
 * `deps` works exactly like useEffect's dependency array: pass the values
 * the fetch depends on (e.g. a route param) so it re-fires when they change.
 */
export function useAsyncData<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    fetcher()
      .then((data) => {
        if (!cancelled) setState({ status: "success", data });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: "error",
            error: error instanceof Error ? error : new Error(String(error)),
          });
        }
      });

    return () => {
      cancelled = true;
    };
    // deps is caller-supplied, mirroring useEffect's own dependency array.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
