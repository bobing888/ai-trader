/**
 * LightweightKlineChart markers — jsdom unit tests.
 *
 * Extends the existing LightweightKlineChart.test.tsx coverage with two tests
 * specifically for the setMarkers integration.
 */

/// <reference types="vitest/globals" />

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LightweightKlineChart } from "@/components/charts/LightweightKlineChart";
import type { Kline } from "@/lib/useRealtimeKlines";

// ── lightweight-charts mock ───────────────────────────────────────────────────

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

// ── fixtures ───────────────────────────────────────────────────────────────────

const SOME_CANDLES: Kline[] = [
  { time: 1700000000, open: 100, high: 105, low: 99, close: 103, volume: 5000 },
  { time: 1700000060, open: 103, high: 107, low: 102, close: 106, volume: 6200 },
  { time: 1700000120, open: 106, high: 108, low: 104, close: 105, volume: 4800 },
];

describe("LightweightKlineChart markers", () => {
  beforeEach(() => {
    mockSetData.mockClear();
    mockSetMarkers.mockClear();
    mockFitContent.mockClear();
  });

  // ── test_markers_passed_to_createChart_setMarkers ──────────────────────────

  it("calls setMarkers when markers prop is provided", () => {
    const markers = [
      {
        time: 1700000060,
        position: "aboveBar" as const,
        color: "#f97316",
        shape: "arrowUp" as const,
        text: "V",
      },
      {
        time: 1700000120,
        position: "aboveBar" as const,
        color: "#3b82f6",
        shape: "circle" as const,
        text: "Vol",
      },
    ];

    render(<LightweightKlineChart candles={SOME_CANDLES} markers={markers} />);

    expect(mockSetMarkers).toHaveBeenCalledTimes(1);
    const [markerData] = mockSetMarkers.mock.calls[0]!;
    expect(markerData).toHaveLength(2);
    expect(markerData[0]).toMatchObject({
      time: 1700000060,
      position: "aboveBar",
      color: "#f97316",
      shape: "arrowUp",
      text: "V",
    });
    expect(markerData[1]).toMatchObject({
      time: 1700000120,
      position: "aboveBar",
      color: "#3b82f6",
      shape: "circle",
      text: "Vol",
    });
  });

  // ── test_no_markers_call_when_prop_empty ──────────────────────────────────

  it("does not call setMarkers when markers prop is empty", () => {
    render(<LightweightKlineChart candles={SOME_CANDLES} markers={[]} />);
    expect(mockSetMarkers).not.toHaveBeenCalled();
  });
});
