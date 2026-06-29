// Renders the agent's live step events. Each event carries a `message` plus
// kind-specific extras the agent attached (query, source counts, plan, totals).
function meta(ev) {
  switch (ev.kind) {
    case "search":
      return ev.query ? `“${ev.query}”` : null;
    case "observation":
      return ev.new_sources != null ? `${ev.new_sources} new source(s)` : null;
    case "plan":
      return Array.isArray(ev.sub_questions)
        ? ev.sub_questions.map((q, i) => `${i + 1}. ${q}`).join("  ·  ")
        : null;
    case "report":
      return ev.sections != null ? `${ev.sections} sections, ${ev.citations} citations` : null;
    case "complete":
      return ev.total_tokens != null
        ? `${ev.total_tokens.toLocaleString()} tokens · $${Number(ev.cost_usd).toFixed(4)}`
        : null;
    case "error":
    case "failed":
      return ev.error || ev.error_code || null;
    default:
      return null;
  }
}

export default function ProgressFeed({ events }) {
  if (!events.length) {
    return <p className="subtle">Waiting for the agent to start…</p>;
  }
  return (
    <ul className="feed">
      {events.map((ev, i) => {
        const extra = meta(ev);
        return (
          <li key={ev.id || i}>
            <span className={`kind ${ev.kind}`}>{ev.kind}</span>
            <span className="msg">
              {ev.message}
              {extra && <div className="meta">{extra}</div>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
