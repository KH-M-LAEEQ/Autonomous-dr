import type { AsyncState } from "../lib/useAsyncData";

/**
 * Renders the loading/error half of useAsyncData's three states. Pages
 * render this and return early; the success case is each page's own data,
 * so it never comes through here.
 */
export function AsyncStatus({
  state,
  loadingLabel,
}: {
  state: Exclude<AsyncState<unknown>, { status: "success" }>;
  loadingLabel: string;
}) {
  if (state.status === "loading") {
    return <p className="text-sm text-muted">{loadingLabel}</p>;
  }
  return (
    <p className="text-sm text-danger" role="alert">
      <span aria-hidden="true">■</span> Couldn't load this page: {state.error.message}
    </p>
  );
}
