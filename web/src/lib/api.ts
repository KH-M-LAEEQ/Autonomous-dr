import type { HealthResponse, ReadyResponse } from "./types";

/**
 * Same-origin fetches only. Vite proxies them to FastAPI in dev (vite.config.ts),
 * and in production the API is served behind the same host — so there is never a
 * backend URL to configure per environment.
 */
async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return (await response.json()) as T;
}

export const getHealth = () => getJson<HealthResponse>("/health");
export const getReady = () => getJson<ReadyResponse>("/ready");
