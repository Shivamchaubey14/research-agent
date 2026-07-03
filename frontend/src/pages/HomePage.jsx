import { useCallback, useEffect, useState } from "react";
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

// Local YYYY-MM-DD (not UTC, so the day doesn't shift across timezones).
function ymd(date) {
  const p = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}

// A preset spanning the last `days` days through today (both inclusive).
function lastDays(days) {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - (days - 1));
  return { after: ymd(from), before: ymd(to) };
}

export default function HomePage() {
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [depth, setDepth] = useState("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [runs, setRuns] = useState(null);
  const [loading, setLoading] = useState(false);
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");

  const filtered = Boolean(after || before);

  const loadRuns = useCallback(() => {
    setLoading(true);
    api
      .listRuns({ after, before })
      .then(setRuns)
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
  }, [after, before]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  function clearFilter() {
    setAfter("");
    setBefore("");
  }

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
        <div className="history-head">
          <h2>History</h2>
          {Array.isArray(runs) && (
            <span className="subtle history-count">
              {runs.length} {runs.length === 1 ? "run" : "runs"}
              {filtered ? " in range" : ""}
            </span>
          )}
        </div>

        <div className="filter-bar">
          <div className="field">
            <label htmlFor="after">From</label>
            <input
              id="after"
              type="date"
              value={after}
              max={before || undefined}
              onChange={(e) => setAfter(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="before">To</label>
            <input
              id="before"
              type="date"
              value={before}
              min={after || undefined}
              onChange={(e) => setBefore(e.target.value)}
            />
          </div>
          <div className="filter-presets">
            <button type="button" className="chip" onClick={() => { const r = lastDays(1); setAfter(r.after); setBefore(r.before); }}>
              Today
            </button>
            <button type="button" className="chip" onClick={() => { const r = lastDays(7); setAfter(r.after); setBefore(r.before); }}>
              7 days
            </button>
            <button type="button" className="chip" onClick={() => { const r = lastDays(30); setAfter(r.after); setBefore(r.before); }}>
              30 days
            </button>
            <button type="button" className="chip" onClick={clearFilter} disabled={!filtered}>
              Clear
            </button>
          </div>
        </div>

        {runs === null ? (
          <p className="subtle">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="subtle">
            {filtered
              ? "No runs in this date range."
              : "No runs yet — start one above."}
          </p>
        ) : (
          <ul className="run-list" style={{ opacity: loading ? 0.5 : 1 }}>
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
