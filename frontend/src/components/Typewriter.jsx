import { useEffect, useRef } from "react";

import { useTypewriter } from "../hooks/useTypewriter.js";

// Renders `text` with a typewriter reveal and a blinking cursor while typing.
// Click to skip to the full text. `onDone` fires once when the reveal finishes
// (also immediately when animation is off) — used to chain sequential reveals.
export default function Typewriter({
  text = "",
  animate = true,
  cps,
  maxMs,
  cursor = true,
  className = "",
  onDone,
}) {
  const { revealed, done, skip } = useTypewriter(text, { animate, cps, maxMs });
  const fired = useRef(false);

  useEffect(() => {
    fired.current = false;
  }, [text]);

  useEffect(() => {
    if (done && !fired.current) {
      fired.current = true;
      onDone?.();
    }
  }, [done, onDone]);

  return (
    <span
      className={`tw ${className}`.trim()}
      onClick={done ? undefined : skip}
      role={done ? undefined : "button"}
      title={done ? undefined : "Click to reveal"}
    >
      {revealed}
      {cursor && !done && <span className="tw-cursor" aria-hidden="true" />}
    </span>
  );
}
