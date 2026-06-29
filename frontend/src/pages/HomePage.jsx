import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client.js";
import StatusBadge from "../components/StatusBadge.jsx";

const DEPTHS = [
  { value: "quick", label: "Quick" },
  { value: "standard", label: "Standard" },
  { value: "deep", label: "Deep" },
];

function when(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function HomePage() {
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [depth, setDepth] = useState("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState(null);

  useEffect(() => {
    api
      .listRuns()
      .then(setRuns)
      .catch(() => setRuns([]));
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError("");
    try {
      const run = await api.createRun(question.trim(), depth);
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(err.message || "Could not start the run");
      setBusy(false);
    }
  }

  return (
    <div className="container stack">
      <form className="card stack" onSubmit={onSubmit}>
        <div>
          <h1>New research</h1>
          <p className="subtle">
            Ask a question — the agent plans, searches, verifies and cites.
          </p>
        </div>
        <div className="field">
          <label htmlFor="q">Question</label>
          <textarea
            id="q"
            maxLength={2000}
            placeholder="e.g. Compare Kafka and RabbitMQ for an event-driven backend"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </div>
        <div className="row">
          <div className="field" style={{ flex: "0 0 200px" }}>
            <label htmlFor="depth">Depth</label>
            <select id="depth" value={depth} onChange={(e) => setDepth(e.target.value)}>
              {DEPTHS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }} />
          <button type="submit" disabled={busy || !question.trim()} style={{ flex: "0 0 auto" }}>
            {busy ? "Starting…" : "Start research"}
          </button>
        </div>
        {error && <div className="error">{error}</div>}
      </form>

      <div className="card">
        <h2>History</h2>
        {runs === null ? (
          <p className="subtle">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="subtle">No runs yet — start one above.</p>
        ) : (
          <ul className="run-list">
            {runs.map((r) => (
              <li key={r.id}>
                <Link to={`/runs/${r.id}`}>
                  <StatusBadge status={r.status} />
                  <span className="q">{r.question}</span>
                  <span className="when">{when(r.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
