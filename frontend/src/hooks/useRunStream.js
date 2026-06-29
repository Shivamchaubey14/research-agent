import { useEffect, useRef, useState } from "react";

import { api } from "../api/client.js";

const TERMINAL = new Set(["complete", "failed", "cancelled"]);
// Named SSE events the backend emits (see research/streaming.py + the agent).
const KINDS = [
  "queued",
  "status",
  "plan",
  "search",
  "observation",
  "reasoning",
  "verification",
  "report",
  "error",
  "complete",
  "failed",
  "cancelled",
];

// Subscribe to a run's SSE progress stream. Replays from the start (last_id=0)
// so a page load shows the full history, then tails live events. Closes on the
// terminal event. Returns the accumulated events plus terminal/connection state.
export function useRunStream(id, enabled = true) {
  const [events, setEvents] = useState([]);
  const [terminal, setTerminal] = useState(null);
  const [reconnecting, setReconnecting] = useState(false);
  const esRef = useRef(null);

  useEffect(() => {
    if (!id || !enabled) return undefined;

    setEvents([]);
    setTerminal(null);
    setReconnecting(false);

    const es = new EventSource(api.eventsUrl(id, "0"));
    esRef.current = es;

    const handle = (kind) => (e) => {
      setReconnecting(false);
      let payload = {};
      try {
        payload = JSON.parse(e.data);
      } catch {
        /* heartbeat / malformed — ignore */
      }
      setEvents((prev) => [...prev, { id: e.lastEventId, kind, ...payload }]);
      if (TERMINAL.has(kind)) {
        setTerminal(kind);
        es.close();
      }
    };

    KINDS.forEach((kind) => es.addEventListener(kind, handle(kind)));
    es.onerror = () => {
      // CONNECTING means the browser is auto-retrying; CLOSED is fatal.
      if (es.readyState === EventSource.CONNECTING) setReconnecting(true);
    };

    return () => es.close();
  }, [id, enabled]);

  return { events, terminal, reconnecting };
}
