/**
 * Mirrors of the API contract. These are hand-written on purpose for Week 1.
 *
 * From Week 2 the source of truth is `docs/api/openapi.json` — generate types from
 * it rather than editing this file by hand, so the frontend cannot silently drift
 * from the backend. See docs/api/README.md.
 */

export interface HealthResponse {
  status: string;
  version: string;
  env: string;
}

export interface ReadyResponse {
  ready: boolean;
  postgres: boolean;
  influxdb: boolean;
  /** Which implementation of each frozen interface is live right now. */
  config: Record<string, string>;
}

/** The frozen WebSocket envelope. Every push from the backend has this shape. */
export type EventType =
  | "hello"
  | "echo"
  | "metric"
  | "incident"
  | "action"
  | "vote"
  | "explanation";

export interface ServerEvent {
  type: EventType;
  tenant_id?: string;
  payload: Record<string, unknown>;
  ts?: string;
}

export type ConnectionState = "connecting" | "open" | "closed";
