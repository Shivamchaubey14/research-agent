// Vitest global setup: jest-dom matchers + jsdom shims for browser APIs the
// components use that jsdom doesn't implement. Runs before every test file.
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount React trees between tests so queries don't see stale DOM.
afterEach(() => {
  cleanup();
  localStorage.clear();
});

// jsdom has no matchMedia. Default to "motion allowed" (matches: false) so the
// typewriter animates; individual tests override this when they need the
// reduced-motion / instant path.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

// jsdom has no ResizeObserver (used by ProgressFeed to measure the card width).
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
