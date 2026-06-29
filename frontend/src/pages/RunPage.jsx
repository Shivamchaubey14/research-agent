import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client.js";
import ProgressFeed from "../components/ProgressFeed.jsx";
import ReportView from "../components/ReportView.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useRunStream } from "../hooks/useRunStream.js";

const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

export default function RunPage() {
  const { id } = useParams();
  const [run, setRun] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const { events, terminal, reconnecting } = useRunStream(id);

  // Load the run once for the question + initial status.
  useEffect(() => {
    api.getRun(id).then(setRun).catch(() => setRun(null));
  }, [id]);

  // When the stream signals a terminal event, refetch the authoritative run
  // (final status, report, token usage and cost).
  useEffect(() => {
    if (terminal) api.getRun(id).then(setRun).catch(() => {});
  }, [terminal, id]);

  const status = run?.status;
  const isTerminal = status ? TERMINAL_STATUSES.has(status) : false;

  async function onCancel() {
    setCancelling(true);
    try {
      const updated = await api.cancelRun(id);
      setRun(updated);
    } catch {
      /* already terminal or transient — the stream will reconcile */
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div className="container stack">
      <div className="card">
        <p className="subtle">
          <Link to="/">← All runs</Link>
        </p>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <h1 style={{ flex: 1 }}>{run?.question || "Run"}</h1>
          <StatusBadge status={status} />
        </div>
        {run?.depth && <p className="subtle">Depth: {run.depth}</p>}
        {!isTerminal && (
          <div style={{ marginTop: 8 }}>
            <button className="danger" onClick={onCancel} disabled={cancelling}>
              {cancelling ? "Cancelling…" : "Cancel run"}
            </button>
          </div>
        )}
        {run?.status === "FAILED" && run?.error && (
          <div className="error">{run.error}</div>
        )}
      </div>

      <div className="card">
        <h2>Progress</h2>
        <ProgressFeed events={events} />
        {reconnecting && <p className="subtle">Reconnecting…</p>}
      </div>

      {run?.report && (
        <div className="card">
          <ReportView run={run} />
        </div>
      )}
    </div>
  );
}
