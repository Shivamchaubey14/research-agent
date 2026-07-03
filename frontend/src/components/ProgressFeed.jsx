import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";

import Typewriter from "./Typewriter.jsx";

gsap.registerPlugin(MotionPathPlugin);

// Serpentine roadmap: numbered nodes fill a row left→right, then the road
// U-turns and the next row runs right→left, so any number of steps fit the card
// width without horizontal scroll. Step *text* lives in the caption below the
// road — the path itself stays clean.
const PADX = 58; // horizontal inset
const PADTOP = 40; // top inset
const ROW = 94; // vertical gap between rows
const COL = 124; // desired horizontal gap between nodes
const BOTTOM = 34; // room under the last row

// Once one of these arrives the run is finished (report generated / stopped).
const TERMINAL = new Set(["complete", "failed", "cancelled"]);

// Kind-specific extras the agent attaches to each step event.
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

// A smooth curve (Catmull-Rom → cubic bézier) through the node points — the
// straight rows stay straight and the row-ends round into U-turns.
function smoothPath(pts) {
  if (pts.length < 2) return "";
  const d = [`M ${pts[0].x} ${pts[0].y}`];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d.push(`C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`);
  }
  return d.join(" ");
}

// Fraction (0..1) along `path` closest to point `pt` — used to place the comet
// at a given node so it can advance from one node to the next.
function nodeFraction(path, pt) {
  const total = path.getTotalLength();
  if (!total) return 0;
  let bestL = 0;
  let best = Infinity;
  const N = 200;
  for (let i = 0; i <= N; i++) {
    const L = (total * i) / N;
    const p = path.getPointAtLength(L);
    const dx = p.x - pt.x;
    const dy = p.y - pt.y;
    const dd = dx * dx + dy * dy;
    if (dd < best) {
      best = dd;
      bestL = L;
    }
  }
  return bestL / total;
}

export default function ProgressFeed({ events }) {
  const wrapRef = useRef(null);
  const rootRef = useRef(null);
  const lineRef = useRef(null);
  const cometRef = useRef(null);
  const prevLenRef = useRef(0);
  const prevWidthRef = useRef(0);
  const prevNRef = useRef(0);
  const cometTweenRef = useRef(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState(null);
  const [cometStep, setCometStep] = useState(0); // node the comet is currently nearest
  const cometStepRef = useRef(0);
  const [selected, setSelected] = useState(null); // node pinned by a click

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const n = events.length;
  const done = n > 0 && TERMINAL.has(events[n - 1].kind);
  const W = width || 720;

  const selectStep = (i) => {
    setSelected((prev) => (prev === i ? null : i)); // click again to deselect
  };

  // A new step arriving resumes the live tour (drop any manual pin).
  const nRef = useRef(n);
  useEffect(() => {
    if (nRef.current !== n) {
      nRef.current = n;
      setSelected(null);
    }
  }, [n]);
  const perRow = Math.max(2, Math.floor((W - 2 * PADX) / COL) + 1);
  const colStep = perRow > 1 ? (W - 2 * PADX) / (perRow - 1) : 0;
  const rows = Math.max(1, Math.ceil(n / perRow));
  const H = PADTOP + (rows - 1) * ROW + BOTTOM;

  const layout = useMemo(
    () =>
      events.map((_, i) => {
        const r = Math.floor(i / perRow);
        let c = i % perRow;
        if (r % 2 === 1) c = perRow - 1 - c; // reverse odd rows (serpentine)
        return { x: PADX + c * colStep, y: PADTOP + r * ROW };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [n, perRow, colStep]
  );
  const d = useMemo(() => smoothPath(layout), [layout]);

  // Draw the road and advance the glowing comet to the newest node.
  useLayoutEffect(() => {
    const line = lineRef.current;
    const comet = cometRef.current;
    if (!line || n < 2) {
      prevLenRef.current = 0;
      prevWidthRef.current = W;
      prevNRef.current = n;
      return undefined;
    }
    const widthChanged = prevWidthRef.current !== W;
    if (widthChanged) prevLenRef.current = 0;
    prevWidthRef.current = W;

    const ctx = gsap.context(() => {
      const len = line.getTotalLength();
      const prev = prevLenRef.current;
      gsap.fromTo(
        line,
        { strokeDasharray: len, strokeDashoffset: Math.max(0, len - prev) },
        { strokeDashoffset: 0, duration: 0.7, ease: "power2.out" }
      );
      prevLenRef.current = len;

      cometTweenRef.current?.kill();
      if (comet) {
        gsap.set(comet, { opacity: 1 });
        // Drive the caption to whichever node the comet is nearest, so it
        // narrates the step the comet is currently at.
        const followCaption = () => {
          const cx = gsap.getProperty(comet, "x");
          const cy = gsap.getProperty(comet, "y");
          let idx = 0;
          let best = Infinity;
          for (let i = 0; i < layout.length; i++) {
            const dx = layout[i].x - cx;
            const dy = layout[i].y - cy;
            const dd = dx * dx + dy * dy;
            if (dd < best) {
              best = dd;
              idx = i;
            }
          }
          if (idx !== cometStepRef.current) {
            cometStepRef.current = idx;
            setCometStep(idx);
          }
        };
        // The comet is a forward progress marker: it advances from the previous
        // frontier node to the newest one and rests there — it never loops back
        // to the start. On a reflow/first paint it simply sweeps in from node 1.
        const grew = !widthChanged && prevNRef.current >= 2 && n > prevNRef.current;
        const startF = grew ? nodeFraction(line, layout[prevNRef.current - 1]) : 0;
        cometTweenRef.current = gsap.to(comet, {
          duration: Math.max(0.9, (1 - startF) * n * 0.9), // gentle pace
          ease: "power2.out",
          motionPath: { path: line, align: line, alignOrigin: [0.5, 0.5], start: startF, end: 1 },
          onUpdate: followCaption,
          onComplete: () => {
            cometStepRef.current = n - 1;
            setCometStep(n - 1);
          },
        });
      }
      prevNRef.current = n;
    }, rootRef);

    return () => ctx.revert();
  }, [n, d, W]);

  if (!n) {
    return (
      <div ref={wrapRef}>
        <p className="subtle">Waiting for the agent to start…</p>
      </div>
    );
  }

  const last = n - 1;
  // Priority: hover preview → pinned click → the comet's current node (which
  // advances to the newest step and rests there).
  const shown =
    hover != null && hover < n
      ? hover
      : selected != null && selected < n
        ? selected
        : Math.min(cometStep, last);
  const cur = events[shown];
  const curMeta = meta(cur);

  return (
    <div className="roadmap-wrap" ref={wrapRef}>
      <div className="roadmap" ref={rootRef} style={{ height: H }}>
        <svg className="roadmap-svg" width={W} height={H} viewBox={`0 0 ${W} ${H}`} fill="none">
          <defs>
            <linearGradient id="rm-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#a5af79" />
              <stop offset="0.5" stopColor="#e8a07c" />
              <stop offset="1" stopColor="#618764" />
            </linearGradient>
          </defs>
          {n > 1 && (
            <>
              <path d={d} className="rm-track" />
              <path d={d} ref={lineRef} className="rm-line" />
              <circle ref={cometRef} className="rm-comet" r="6" cx="0" cy="0" opacity="0" />
            </>
          )}
        </svg>

        {layout.map((pt, i) => {
          const ev = events[i];
          const cls = [
            "rm-dot",
            ev.kind,
            i === last ? "is-active" : "",
            i === selected ? "is-selected" : i === shown ? "is-shown" : "",
          ]
            .join(" ")
            .trim();
          return (
            <span
              key={ev.id || i}
              className={cls}
              style={{ left: pt.x, top: pt.y }}
              role="button"
              tabIndex={0}
              aria-label={`Step ${i + 1}: ${ev.kind} — ${ev.message}`}
              aria-pressed={i === selected}
              onClick={() => selectStep(i)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  selectStep(i);
                }
              }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              {i + 1}
            </span>
          );
        })}
      </div>

      <div className={`rm-caption ${selected != null ? "is-pinned" : ""}`}>
        <span className="rm-cap-step">{shown + 1}</span>
        <span className={`rm-cap-kind ${cur.kind}`}>{cur.kind}</span>
        <div className="rm-cap-body">
          <Typewriter
            key={shown}
            className="rm-cap-msg"
            text={cur.message || ""}
            animate={hover == null && selected == null}
            cps={90}
            maxMs={900}
          />
          {curMeta && <div className="rm-cap-meta">{curMeta}</div>}
        </div>
      </div>
      {n > 1 && (
        <p className="rm-hint subtle">
          {selected != null
            ? "Pinned — click this node again to resume."
            : done
              ? "Click a node to see what happened at that step."
              : "The agent is working — click a node to inspect a step."}
        </p>
      )}
    </div>
  );
}
