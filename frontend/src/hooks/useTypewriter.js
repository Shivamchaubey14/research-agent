import { useEffect, useState } from "react";

// Respect the OS "reduce motion" setting — skip the animation entirely.
function prefersReduced() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

// Progressively reveals `text` for a typewriter effect. `cps` sets the base
// speed (chars/second); `maxMs` caps the total duration so long text still
// finishes promptly (chars-per-tick scales up as needed). Returns the revealed
// slice, a `done` flag, and `skip()` to reveal everything at once.
export function useTypewriter(text, { animate = true, cps = 55, maxMs = 4000 } = {}) {
  const full = text ? text.length : 0;
  const instant = !animate || full === 0 || prefersReduced();
  const [n, setN] = useState(instant ? full : 0);
  const [done, setDone] = useState(instant);

  useEffect(() => {
    if (instant) {
      setN(full);
      setDone(true);
      return undefined;
    }
    setN(0);
    setDone(false);
    const tick = 24; // ms between reveals (~42fps)
    const byCps = Math.max(1, Math.round((cps * tick) / 1000));
    const byCap = Math.ceil(full / Math.max(1, maxMs / tick));
    const step = Math.max(byCps, byCap); // chars revealed per tick
    let i = 0;
    const timer = setInterval(() => {
      i += step;
      if (i >= full) {
        setN(full);
        setDone(true);
        clearInterval(timer);
      } else {
        setN(i);
      }
    }, tick);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, animate]);

  const skip = () => {
    setN(full);
    setDone(true);
  };

  return { revealed: text ? text.slice(0, n) : "", done, skip };
}
