import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StatusBadge from "./StatusBadge.jsx";

describe("StatusBadge", () => {
  it("renders nothing without a status", () => {
    const { container } = render(<StatusBadge />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the lowercased status and keeps the raw status as a class", () => {
    render(<StatusBadge status="RUNNING" />);
    const badge = screen.getByText("running");
    expect(badge).toHaveClass("badge", "RUNNING");
  });
});
