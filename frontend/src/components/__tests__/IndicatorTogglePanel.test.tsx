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
  it("renders MA series + BOLL toggles with current enabled state", () => {
    render(
      <IndicatorTogglePanel prefs={basePrefs} onChange={vi.fn()} />,
    );
    expect(screen.getByTestId("indicator-toggle-ma5")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("indicator-toggle-ma10")).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("indicator-toggle-ma20")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("indicator-toggle-ma30")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("indicator-toggle-ma60")).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("indicator-toggle-boll")).toHaveAttribute("aria-checked", "true");
  });

  it("shows color swatch + label per indicator", () => {
    render(<IndicatorTogglePanel prefs={basePrefs} onChange={vi.fn()} />);
    const ma5Row = screen.getByTestId("indicator-row-ma5");
    expect(within(ma5Row).getByText("MA 5")).toBeTruthy();
    expect(within(ma5Row).getByTestId("indicator-swatch-ma5")).toBeTruthy();
  });

  it("fires onChange with the toggled indicator id when clicked", () => {
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
});
