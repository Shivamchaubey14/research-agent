import { useLayoutEffect, useRef, useState } from "react";
import { gsap } from "gsap";

import Typewriter from "./Typewriter.jsx";

// Renders a completed run's report: summary, ordered sections, and the
// resolvable citation list (FR-RPT-1, FR-RPT-2). The summary types out first,
// then each section in turn, then the sources — so the report "writes itself".
export default function ReportView({ run }) {
  const report = run?.report;
  const [stage, setStage] = useState(0);
  const rootRef = useRef(null);

  const sections = report?.sections || [];
  const hasSummary = Boolean(report?.summary);
  const sectionBase = hasSummary ? 1 : 0;
  const blockCount = sectionBase + sections.length;

  // Gently raise each block into view as it becomes the active stage. fromTo
  // (not from) pins the end state to opacity:1 so a StrictMode double-invoke in
  // dev can't leave the block stuck faded.
  useLayoutEffect(() => {
    if (!rootRef.current) return;
    const el = rootRef.current.querySelector(`[data-stage="${stage}"]`);
    if (el) {
      gsap.fromTo(
        el,
        { y: 14, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.5, ease: "power3.out", overwrite: "auto" }
      );
    }
  }, [stage]);

  if (!report) return null;

  const advance = (from) => setStage((s) => Math.max(s, from + 1));

  return (
    <div className="report" ref={rootRef}>
      <h2>Report</h2>

      {hasSummary && (
        <p data-stage={0}>
          <Typewriter
            text={report.summary}
            cps={70}
            maxMs={2600}
            onDone={() => advance(0)}
          />
        </p>
      )}

      {sections.map((s, i) => {
        const st = sectionBase + i;
        if (stage < st) return null;
        return (
          <section key={i} data-stage={st}>
            <h3>{s.heading}</h3>
            <p>
              <Typewriter
                text={s.content}
                cps={70}
                maxMs={2800}
                animate={stage === st}
                onDone={() => advance(st)}
              />
            </p>
          </section>
        );
      })}

      {stage >= blockCount && (
        <>
          {report.citations?.length > 0 && (
            <section data-stage={blockCount}>
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
        </>
      )}
    </div>
  );
}
