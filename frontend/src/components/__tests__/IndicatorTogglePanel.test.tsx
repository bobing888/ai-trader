import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { IndicatorTogglePanel } from "@/components/IndicatorTogglePanel";
import type { IndicatorDef } from "@/components/IndicatorTogglePanel.types";
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

// 默认 6 行 defs — 与旧硬编码 ROWS 对齐
const defaultDefs: IndicatorDef[] = [
  { id: "ma5",  label: "MA 5",  color: "#fbbf24", overlay: true },
  { id: "ma10", label: "MA 10", color: "#60a5fa", overlay: true },
  { id: "ma20", label: "MA 20", color: "#34d399", overlay: true },
  { id: "ma30", label: "MA 30", color: "#f87171", overlay: true },
  { id: "ma60", label: "MA 60", color: "#a78bfa", overlay: true },
  { id: "boll", label: "BOLL 布林带", color: "#fbbf24", overlay: true, style: "dashed" },
];

describe("IndicatorTogglePanel", () => {
  it("renders MA series + BOLL chips with current enabled state (aria-pressed)", () => {
    render(
      <IndicatorTogglePanel prefs={basePrefs} defs={defaultDefs} onChange={vi.fn()} />,
    );
    expect(screen.getByTestId("indicator-toggle-ma5")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-ma10")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("indicator-toggle-ma20")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-ma30")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-ma60")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("indicator-toggle-boll")).toHaveAttribute("aria-pressed", "true");
  });

  it("shows color swatch + label per indicator", () => {
    render(<IndicatorTogglePanel prefs={basePrefs} defs={defaultDefs} onChange={vi.fn()} />);
    const ma5Chip = screen.getByTestId("indicator-toggle-ma5");
    expect(within(ma5Chip).getByTestId("indicator-row-ma5")).toHaveTextContent("MA 5");
    expect(within(ma5Chip).getByTestId("indicator-swatch-ma5")).toBeTruthy();
  });

  it("fires onChange with the toggled indicator id when clicked (off → on, on → off)", () => {
    const onChange = vi.fn();
    render(<IndicatorTogglePanel prefs={basePrefs} defs={defaultDefs} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("indicator-toggle-ma10"));
    expect(onChange).toHaveBeenCalledWith("ma10", true);
    fireEvent.click(screen.getByTestId("indicator-toggle-ma20"));
    expect(onChange).toHaveBeenCalledWith("ma20", false);
  });

  it("fires onChange for BOLL toggle (single click controls 3 lines)", () => {
    const onChange = vi.fn();
    render(<IndicatorTogglePanel prefs={basePrefs} defs={defaultDefs} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("indicator-toggle-boll"));
    expect(onChange).toHaveBeenCalledWith("boll", false);
  });

  it("renders as a stacked column of horizontal chip rows (overlay + subpane sections)", () => {
    render(<IndicatorTogglePanel prefs={basePrefs} defs={defaultDefs} onChange={vi.fn()} />);
    const root = screen.getByTestId("indicator-toggle-panel");
    expect(root.className).toMatch(/flex-col/);
    expect(root).toHaveAttribute("role", "toolbar");
    const overlaySection = screen.getByTestId("indicator-section-overlay");
    expect(overlaySection.className).toMatch(/flex-row/);
    expect(overlaySection.className).toMatch(/items-center/);
  });

  it("each chip is a native <button> with cursor-pointer (one-click toggling)", () => {
    render(<IndicatorTogglePanel prefs={basePrefs} defs={defaultDefs} onChange={vi.fn()} />);
    const chip = screen.getByTestId("indicator-toggle-ma5");
    expect(chip.tagName).toBe("BUTTON");
    expect(chip).toHaveClass("cursor-pointer");
  });

  it("clicking chip fires onChange with the new state (off → on)", () => {
    const onChange = vi.fn();
    render(<IndicatorTogglePanel prefs={basePrefs} defs={defaultDefs} onChange={onChange} />);
    const chip = screen.getByTestId("indicator-toggle-ma10");
    expect(chip).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(chip);
    expect(onChange).toHaveBeenLastCalledWith("ma10", true);
  });

  // ── 新需求：合并 8 个指标到同一面板，按 overlay 分两组 ─────────────────────
  const unifiedDefs: IndicatorDef[] = [
    { id: "ma30",  label: "MA 30", color: "#f87171", overlay: true },
    { id: "boll",  label: "BOLL",  color: "#fbbf24", overlay: true, style: "dashed" },
    { id: "rsi",   label: "RSI 14", color: "#fb923c", overlay: false },
    { id: "rsi6",  label: "RSI 6",  color: "#fbbf24", overlay: false },
    { id: "rsi24", label: "RSI 24", color: "#f97316", overlay: false },
    { id: "macd",  label: "MACD",   color: "#38bdf8", overlay: false },
    { id: "kdj",   label: "KDJ",    color: "#fb923c", overlay: false },
    { id: "stoch", label: "Stoch",  color: "#fb923c", overlay: false },
  ];

  const unifiedPrefs: ChartPreferences = {
    indicators: {
      ma30:  { enabled: true,  params: { length: 30 } },
      boll:  { enabled: true,  params: { length: 20, mult: 2.0 } },
      rsi:   { enabled: true,  params: { length: 14 } },
      rsi6:  { enabled: false, params: { length: 6 } },
      rsi24: { enabled: false, params: { length: 24 } },
      macd:  { enabled: true,  params: { fast: 12, slow: 26, signal: 9 } },
      kdj:   { enabled: true,  params: { length: 9 } },
      stoch: { enabled: false, params: { k: 14, d: 3 } },
    } as Record<string, IndicatorPref>,
  };

  it("renders chips for all 8 unified indicators (MA30/BOLL/RSI14/RSI6/RSI24/MACD/KDJ/Stoch)", () => {
    render(<IndicatorTogglePanel prefs={unifiedPrefs} defs={unifiedDefs} onChange={vi.fn()} />);
    for (const id of ["ma30", "boll", "rsi", "rsi6", "rsi24", "macd", "kdj", "stoch"]) {
      expect(screen.getByTestId(`indicator-toggle-${id}`)).toBeTruthy();
    }
  });

  it("groups indicators into overlay section + subpane section by overlay flag", () => {
    render(<IndicatorTogglePanel prefs={unifiedPrefs} defs={unifiedDefs} onChange={vi.fn()} />);
    expect(screen.getByTestId("indicator-section-overlay")).toBeTruthy();
    expect(screen.getByTestId("indicator-section-subpane")).toBeTruthy();
    const overlaySection = screen.getByTestId("indicator-section-overlay");
    expect(within(overlaySection).getByTestId("indicator-toggle-ma30")).toBeTruthy();
    expect(within(overlaySection).getByTestId("indicator-toggle-boll")).toBeTruthy();
    expect(within(overlaySection).queryByTestId("indicator-toggle-rsi")).toBeNull();
    const subpaneSection = screen.getByTestId("indicator-section-subpane");
    expect(within(subpaneSection).getByTestId("indicator-toggle-rsi")).toBeTruthy();
    expect(within(subpaneSection).getByTestId("indicator-toggle-rsi6")).toBeTruthy();
    expect(within(subpaneSection).getByTestId("indicator-toggle-rsi24")).toBeTruthy();
    expect(within(subpaneSection).getByTestId("indicator-toggle-macd")).toBeTruthy();
    expect(within(subpaneSection).getByTestId("indicator-toggle-kdj")).toBeTruthy();
    expect(within(subpaneSection).getByTestId("indicator-toggle-stoch")).toBeTruthy();
    expect(within(subpaneSection).queryByTestId("indicator-toggle-ma30")).toBeNull();
  });

  it("reflects enabled state for subpane indicators (RSI6 off, RSI14 on, MACD on)", () => {
    render(<IndicatorTogglePanel prefs={unifiedPrefs} defs={unifiedDefs} onChange={vi.fn()} />);
    expect(screen.getByTestId("indicator-toggle-rsi")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-rsi6")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("indicator-toggle-rsi24")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("indicator-toggle-macd")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-kdj")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("indicator-toggle-stoch")).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking subpane chip fires onChange with id + new enabled state", () => {
    const onChange = vi.fn();
    render(<IndicatorTogglePanel prefs={unifiedPrefs} defs={unifiedDefs} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("indicator-toggle-rsi6"));
    expect(onChange).toHaveBeenLastCalledWith("rsi6", true);
    fireEvent.click(screen.getByTestId("indicator-toggle-macd"));
    expect(onChange).toHaveBeenLastCalledWith("macd", false);
  });

  it("context menu (right-click) on chip fires onEditParams(id) when provided", () => {
    const onEditParams = vi.fn();
    render(
      <IndicatorTogglePanel
        prefs={unifiedPrefs}
        defs={unifiedDefs}
        onChange={vi.fn()}
        onEditParams={onEditParams}
      />,
    );
    fireEvent.contextMenu(screen.getByTestId("indicator-toggle-rsi"));
    expect(onEditParams).toHaveBeenCalledWith("rsi");
  });

  it("double click on chip fires onEditParams(id) when provided", () => {
    const onEditParams = vi.fn();
    render(
      <IndicatorTogglePanel
        prefs={unifiedPrefs}
        defs={unifiedDefs}
        onChange={vi.fn()}
        onEditParams={onEditParams}
      />,
    );
    fireEvent.doubleClick(screen.getByTestId("indicator-toggle-macd"));
    expect(onEditParams).toHaveBeenCalledWith("macd");
  });

  it("does NOT fire onEditParams when prop is not provided (no crash)", () => {
    render(<IndicatorTogglePanel prefs={unifiedPrefs} defs={unifiedDefs} onChange={vi.fn()} />);
    expect(() => {
      fireEvent.contextMenu(screen.getByTestId("indicator-toggle-rsi"));
      fireEvent.doubleClick(screen.getByTestId("indicator-toggle-boll"));
    }).not.toThrow();
  });
});
