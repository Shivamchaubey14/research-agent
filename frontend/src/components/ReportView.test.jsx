import { render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";

// gsap only drives entrance animations here — stub it so the staging logic runs
// without a real ticker.
vi.mock("gsap", () => ({
  gsap: { fromTo: vi.fn(), registerPlugin: vi.fn() },
}));

// Replace the typewriter with a stand-in that renders its text and reports done
// from an effect (not during render), so ReportView's stage cascade resolves in
// one settled pass without a setState-in-render warning.
vi.mock("./Typewriter.jsx", () => ({
  default: ({ text, onDone }) => {
    useEffect(() => {
      onDone?.();
    }, [onDone]);
    return <span>{text}</span>;
  },
}));

import ReportView from "./ReportView.jsx";

const run = {
  total_tokens: 1234,
  cost_usd: 0.0123,
  report: {
    summary: "The short answer.",
    sections: [
      { heading: "Background", content: "Some background." },
      { heading: "Details", content: "The details." },
    ],
    citations: [
      { id: 1, marker: 1, url: "https://example.com", title: "Example" },
      { id: 2, marker: 2, doc_ref: "doc-7#3" }, // a document citation, no url
    ],
  },
};

describe("ReportView", () => {
  it("renders nothing when the run has no report", () => {
    const { container } = render(<ReportView run={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the summary, every section, and the sources once all stages advance", () => {
    render(<ReportView run={run} />);

    expect(screen.getByText("The short answer.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Background" })).toBeInTheDocument();
    expect(screen.getByText("Some background.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Details" })).toBeInTheDocument();

    // Web citation renders as a link; document citation falls back to its ref.
    const link = screen.getByRole("link", { name: "Example" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(screen.getByText("doc-7#3")).toBeInTheDocument();
  });

  it("shows the token and cost footer", () => {
    const { container } = render(<ReportView run={run} />);
    const usage = container.querySelector(".usage");
    expect(usage.textContent).toMatch(/tokens/);
    expect(usage.textContent).toContain("$0.0123");
  });
});
