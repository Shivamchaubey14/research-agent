import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

// The roadmap's SVG geometry (getTotalLength / motionPath) isn't implemented by
// jsdom, so stub gsap: context() returns a no-op handle and never runs the
// callback that would touch the path, letting the component's layout/caption
// logic be tested on its own.
vi.mock("gsap", () => ({
  gsap: {
    registerPlugin: vi.fn(),
    context: vi.fn(() => ({ revert: vi.fn() })),
    set: vi.fn(),
    to: vi.fn(),
    fromTo: vi.fn(),
    getProperty: vi.fn(() => 0),
  },
}));
vi.mock("gsap/MotionPathPlugin", () => ({ MotionPathPlugin: {} }));

// Render the caption text synchronously instead of typing it out.
vi.mock("./Typewriter.jsx", () => ({
  default: ({ text }) => <span>{text}</span>,
}));

import ProgressFeed from "./ProgressFeed.jsx";

describe("ProgressFeed", () => {
  it("shows a waiting placeholder before any events arrive", () => {
    render(<ProgressFeed events={[]} />);
    expect(screen.getByText(/waiting for the agent/i)).toBeInTheDocument();
  });

  it("captions a single event with its kind and kind-specific meta", () => {
    const events = [{ id: "e1", kind: "search", message: "searching the web", query: "quantum" }];
    render(<ProgressFeed events={events} />);

    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("searching the web")).toBeInTheDocument();
    // meta() renders the query for a search step.
    expect(screen.getByText(/quantum/)).toBeInTheDocument();
    // A single node is drawn.
    expect(screen.getByRole("button", { name: /Step 1:/ })).toBeInTheDocument();
  });

  it("pins a clicked node and captions that step", async () => {
    const user = userEvent.setup();
    const events = [
      { id: "e1", kind: "plan", message: "planning" },
      { id: "e2", kind: "search", message: "searching", query: "q" },
      { id: "e3", kind: "observation", message: "read a page", new_sources: 4 },
    ];
    render(<ProgressFeed events={events} />);

    await user.click(screen.getByRole("button", { name: /Step 3:/ }));

    expect(screen.getByText("observation")).toBeInTheDocument();
    expect(screen.getByText("read a page")).toBeInTheDocument();
    expect(screen.getByText("4 new source(s)")).toBeInTheDocument();
    expect(screen.getByText(/Pinned/)).toBeInTheDocument();
  });
});
