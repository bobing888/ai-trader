import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { IndicatorTogglePanel } from "@/components/IndicatorTogglePanel";
import type { ChartPreferences, IndicatorPref } from "@/lib/preferences";

const basePrefs: ChartPreferences = {
  indicators: {
    ma5:  { enabled: true,  params: { length: 5 } },
    ma10: { enabled: false, params: { length: 10 } },
    ma20: { enabled: true,  params: { length: 20 } },
    ma30: { enabled: true,  params: { length: 30 } },
    ma60: { enabled: false, params: { length: 60 } },
    boll: { enabled: true,  params: { length: 20, mult: 2.0 } },
  } as Record<string, IndicatorPref>,
};

describe("IndicatorTogglePanel", () => {
  it("renders MA series + BOLL chips with current enabled state (aria-pressed)", () => {
    render(
      <IndicatorTogglePanel prefs={basePrefs} onChange={vi.fn()} />,
    );
    expect(screen.getByTestId("indicator-toggle-ma5")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-ma10")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("indicator-toggle-ma20")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-ma30")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-ma60")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("indicator-toggle-boll")).toHaveAttribute("aria-pressed", "true");
  });

  it("shows color swatch + label per indicator", () => {
    render(<IndicatorTogglePanel prefs={basePrefs} onChange={vi.fn()} />);
    const ma5Chip = screen.getByTestId("indicator-toggle-ma5");
    // label + swatch 都内联在 chip 内
    expect(within(ma5Chip).getByTestId("indicator-row-ma5")).toHaveTextContent("MA 5");
    expect(within(ma5Chip).getByTestId("indicator-swatch-ma5")).toBeTruthy();
  });

  it("fires onChange with the toggled indicator id when clicked (off → on, on → off)", () => {
    const onChange = vi.fn();
    render(<IndicatorTogglePanel prefs={basePrefs} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("indicator-toggle-ma10"));
    expect(onChange).toHaveBeenCalledWith("ma10", true);
    fireEvent.click(screen.getByTestId("indicator-toggle-ma20"));
    expect(onChange).toHaveBeenCalledWith("ma20", false);
  });

  it("fires onChange for BOLL toggle (single click controls 3 lines)", () => {
    const onChange = vi.fn();
    render(<IndicatorTogglePanel prefs={basePrefs} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("indicator-toggle-boll"));
    expect(onChange).toHaveBeenCalledWith("boll", false);
  });

  // ── 新需求：chip 行（横向、按钮式） ───────────────────────────────────────
  it("renders as a single horizontal chip row (no outer card / list)", () => {
    render(<IndicatorTogglePanel prefs={basePrefs} onChange={vi.fn()} />);
    const root = screen.getByTestId("indicator-toggle-panel");
    // 根元素是横向 row
    expect(root.className).toMatch(/flex-row/);
    expect(root.className).toMatch(/items-center/);
    expect(root).toHaveAttribute("role", "toolbar");
  });

  it("each chip is a native <button> with cursor-pointer (one-click toggling)", () => {
    render(<IndicatorTogglePanel prefs={basePrefs} onChange={vi.fn()} />);
    const chip = screen.getByTestId("indicator-toggle-ma5");
    expect(chip.tagName).toBe("BUTTON");
    expect(chip).toHaveClass("cursor-pointer");
  });

  it("clicking chip fires onChange with the new state (off → on)", () => {
    const onChange = vi.fn();
    render(<IndicatorTogglePanel prefs={basePrefs} onChange={onChange} />);
    const chip = screen.getByTestId("indicator-toggle-ma10");
    expect(chip).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(chip);
    expect(onChange).toHaveBeenLastCalledWith("ma10", true);
  });
});
