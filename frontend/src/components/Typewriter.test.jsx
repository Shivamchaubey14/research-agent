import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Typewriter from "./Typewriter.jsx";

describe("Typewriter — non-animated", () => {
  it("renders the full text and fires onDone exactly once", () => {
    const onDone = vi.fn();
    render(<Typewriter text="all at once" animate={false} onDone={onDone} />);
    expect(screen.getByText("all at once")).toBeInTheDocument();
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("passes through an extra className", () => {
    render(<Typewriter text="x" animate={false} className="rm-cap-msg" />);
    expect(screen.getByText("x")).toHaveClass("tw", "rm-cap-msg");
  });
});

describe("Typewriter — animated", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("is clickable to skip while typing, then settles and fires onDone", () => {
    const onDone = vi.fn();
    render(<Typewriter text="type me out" animate onDone={onDone} />);

    // Mid-animation the whole text is not shown yet and the node is a button.
    const el = screen.getByRole("button", { name: "Click to reveal" });
    expect(el.textContent).not.toBe("type me out");
    expect(onDone).not.toHaveBeenCalled();

    // Let it finish on its own.
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText("type me out")).toBeInTheDocument();
    expect(onDone).toHaveBeenCalledTimes(1);
    // Once done the skip affordance (button role) is gone.
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("reveals everything immediately when clicked", () => {
    const onDone = vi.fn();
    render(<Typewriter text="skip via click" animate onDone={onDone} />);

    // Synchronous click, timers frozen, so skip() reveals the full text before
    // the animation interval gets another tick to overwrite it.
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("skip via click")).toBeInTheDocument();
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
