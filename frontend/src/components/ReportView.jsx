// Renders a completed run's report: summary, ordered sections, and the
// resolvable citation list (FR-RPT-1, FR-RPT-2).
export default function ReportView({ run }) {
  const report = run?.report;
  if (!report) return null;

  return (
    <div className="report">
      <h2>Report</h2>
      {report.summary && <p>{report.summary}</p>}

      {report.sections?.map((s, i) => (
        <section key={i}>
          <h3>{s.heading}</h3>
          <p>{s.content}</p>
        </section>
      ))}

      {report.citations?.length > 0 && (
        <section>
          <h3>Sources</h3>
          <ul className="citations">
            {report.citations.map((c) => (
              <li key={c.id || c.marker}>
                <span className="marker">[{c.marker}]</span>
                <span>
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noreferrer">
                      {c.title || c.url}
                    </a>
                  ) : (
                    c.title || c.doc_ref || "source"
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="usage">
        {Number(run.total_tokens).toLocaleString()} tokens · $
        {Number(run.cost_usd).toFixed(4)}
      </div>
    </div>
  );
}
