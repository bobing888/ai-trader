/**
 * LightweightKlineChart — jsdom-friendly tests.
 *
 * lightweight-charts v4 uses canvas which is not available in jsdom.
 * We mock the entire module so these tests run in CI without a real browser.
 */

/// <reference types="vitest/globals" />

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LightweightKlineChart } from "@/components/charts/LightweightKlineChart";
import type { Kline } from "@/lib/useRealtimeKlines";

// ── Mock lightweight-charts ──────────────────────────────────────────────────
const mockSetData = vi.fn();
const mockSetMarkers = vi.fn();
const mockFitContent = vi.fn();
const mockRemove = vi.fn();
const mockApplyOptions = vi.fn();

const mockCandleSeries = {
  setData: mockSetData,
  setMarkers: mockSetMarkers,
};

const mockVolumeSeries = {
  setData: mockSetData,
};

const mockChartInstance = {
  addCandlestickSeries: vi.fn(() => mockCandleSeries),
  addHistogramSeries: vi.fn(() => mockVolumeSeries),
  priceScale: vi.fn(() => ({ applyOptions: mockApplyOptions })),
  timeScale: vi.fn(() => ({ fitContent: mockFitContent })),
  subscribeCrosshairMove: vi.fn(),
  applyOptions: mockApplyOptions,
  remove: mockRemove,
};

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => mockChartInstance),
}));

// ── helpers ────────────────────────────────────────────────────────────────
const EMPTY_CANDLES: Kline[] = [];
const SOME_CANDLES: Kline[] = [
  { time: 1700000000, open: 100, high: 105, low: 99, close: 103, volume: 5000 },
  { time: 1700000060, open: 103, high: 107, low: 102, close: 106, volume: 6200 },
  { time: 1700000120, open: 106, high: 108, low: 104, close: 105, volume: 4800 },
];

describe("LightweightKlineChart", () => {
  it("renders without crashing with empty candles", () => {
    render(<LightweightKlineChart candles={EMPTY_CANDLES} />);
    // Component renders a container div — no exception means it works
    const container = document.querySelector('[class*="rounded-2xl"]');
    expect(container).not.toBeNull();
  });

  it("passes candle data to lightweight-charts setData after receiving data", () => {
    // Initial render with empty candles
    const { rerender } = render(<LightweightKlineChart candles={EMPTY_CANDLES} />);

    // Rerender with real data → triggers the data-feeding useEffect
    rerender(<LightweightKlineChart candles={SOME_CANDLES} />);

    // setData should have been called at least once (candle series)
    expect(mockSetData).toHaveBeenCalled();
  });

  it("calls fitContent on chart when candles are first loaded", () => {
    const { rerender } = render(<LightweightKlineChart candles={EMPTY_CANDLES} />);
    mockFitContent.mockClear();

    rerender(<LightweightKlineChart candles={SOME_CANDLES} />);

    // fitContent is called to auto-scale the chart
    expect(mockFitContent).toHaveBeenCalled();
  });

  it("does not call setMarkers when markers array is empty", () => {
    render(<LightweightKlineChart candles={SOME_CANDLES} markers={[]} />);
    expect(mockSetMarkers).not.toHaveBeenCalled();
  });
});
