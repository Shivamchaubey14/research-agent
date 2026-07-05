import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTypewriter } from "./useTypewriter.js";

// Force the OS "reduce motion" query to a given answer for one test.
function setReducedMotion(reduced) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe("useTypewriter — instant paths", () => {
  it("reveals everything immediately when animation is off", () => {
    const { result } = renderHook(() => useTypewriter("hello world", { animate: false }));
    expect(result.current.revealed).toBe("hello world");
    expect(result.current.done).toBe(true);
  });

  it("is done immediately for empty text", () => {
    const { result } = renderHook(() => useTypewriter("", { animate: true }));
    expect(result.current.revealed).toBe("");
    expect(result.current.done).toBe(true);
  });

  it("skips the animation when the OS prefers reduced motion", () => {
    setReducedMotion(true);
    const { result } = renderHook(() => useTypewriter("motion off", { animate: true }));
    expect(result.current.revealed).toBe("motion off");
    expect(result.current.done).toBe(true);
    setReducedMotion(false);
  });
});

describe("useTypewriter — animated reveal", () => {
  beforeEach(() => {
    setReducedMotion(false);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts empty and reveals progressively over time", () => {
    const text = "a".repeat(120);
    const { result } = renderHook(() => useTypewriter(text, { animate: true, cps: 55, maxMs: 4000 }));

    // Nothing revealed on the first frame.
    expect(result.current.revealed).toBe("");
    expect(result.current.done).toBe(false);

    // One char per 24ms tick at these settings — advance five ticks.
    act(() => vi.advanceTimersByTime(24 * 5));
    expect(result.current.revealed.length).toBe(5);
    expect(result.current.done).toBe(false);

    // Advance well past the end — it settles on the full text and marks done.
    act(() => vi.advanceTimersByTime(24 * 200));
    expect(result.current.revealed).toBe(text);
    expect(result.current.done).toBe(true);
  });

  it("caps long text to the max duration by revealing several chars per tick", () => {
    // 5000 chars with a 1000ms cap ⇒ far more than one char per 24ms tick.
    const text = "x".repeat(5000);
    const { result } = renderHook(() => useTypewriter(text, { animate: true, maxMs: 1000 }));

    act(() => vi.advanceTimersByTime(24));
    expect(result.current.revealed.length).toBeGreaterThan(1);

    // Finishes within roughly the cap, not the ~2 minutes one-char-per-tick would take.
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.done).toBe(true);
    expect(result.current.revealed).toBe(text);
  });

  it("skip() jumps straight to the full text", () => {
    const text = "reveal me";
    const { result } = renderHook(() => useTypewriter(text, { animate: true }));
    expect(result.current.done).toBe(false);

    act(() => result.current.skip());
    expect(result.current.revealed).toBe(text);
    expect(result.current.done).toBe(true);
  });
});
