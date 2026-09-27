/**
 * @vitest-environment jsdom
 * ConfluenceDirectionBadge — 单元测试
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfluenceDirectionBadge } from "../ConfluenceDirectionBadge";

describe("ConfluenceDirectionBadge", () => {
  it("direction=long → renders 做多", () => {
    render(<ConfluenceDirectionBadge direction="long" score={50} />);
    expect(screen.getByText(/做多/)).toBeInTheDocument();
  });

  it("direction=short → renders 做空", () => {
    render(<ConfluenceDirectionBadge direction="short" score={50} />);
    expect(screen.getByText(/做空/)).toBeInTheDocument();
  });

  it("direction=mixed → renders 观望", () => {
    render(<ConfluenceDirectionBadge direction="mixed" score={50} />);
    expect(screen.getByText(/观望/)).toBeInTheDocument();
  });

  it("score >= 75 + long → renders 极强", () => {
    render(<ConfluenceDirectionBadge direction="long" score={80} />);
    expect(screen.getByText(/极强/)).toBeInTheDocument();
  });

  it("score >= 60 + long → renders 强信号", () => {
    render(<ConfluenceDirectionBadge direction="long" score={65} />);
    expect(screen.getByText(/强信号/)).toBeInTheDocument();
  });

  it("score < 60 + long → renders 做多 without suffix", () => {
    render(<ConfluenceDirectionBadge direction="long" score={40} />);
    const el = screen.getByText(/做多/);
    expect(el).toBeInTheDocument();
    expect(el.textContent).toBe("做多");
  });
});
