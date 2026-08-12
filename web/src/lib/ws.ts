import { useEffect, useRef, useState } from "react";
import type { ConnectionState, ServerEvent } from "./types";

const RETRY_MS = 2000;
const MAX_BUFFERED = 50;

/**
 * WebSocket client stub (Week 1 deliverable).
 *
 * Reconnects on close, because during development the API restarts constantly and
 * a dashboard that needs a manual refresh after every backend save will be closed
 * and never reopened. Week 6 adds subscriptions and event routing on top of this;
 * the reconnect behaviour should survive that.
 */
export function useEventStream(path = "/ws") {
  const [state, setState] = useState<ConnectionState>("connecting");
  const [events, setEvents] = useState<ServerEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closedByUs = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(`${protocol}//${window.location.host}${path}`);
      socketRef.current = socket;
      setState("connecting");

      socket.onopen = () => setState("open");

      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data as string) as ServerEvent;
          setEvents((previous) => [event, ...previous].slice(0, MAX_BUFFERED));
        } catch {
          // A malformed frame is a backend bug. Drop it here, surface it there.
        }
      };

      socket.onclose = () => {
        setState("closed");
        if (!closedByUs) retry = setTimeout(connect, RETRY_MS);
      };
    };

    connect();

    return () => {
      closedByUs = true;
      if (retry) clearTimeout(retry);
      socketRef.current?.close();
    };
  }, [path]);

  const send = (text: string) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(text);
    }
  };

  return { state, events, send };
}
