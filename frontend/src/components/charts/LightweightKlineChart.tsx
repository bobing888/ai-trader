/**
 * LightweightKlineChart — TradingView lightweight-charts v4 wrapper.
 *
 * Renders a candlestick chart with volume histogram using the ai-trader
 * dark/light theme tokens from index.css.
 *
 * Props:
 *   candles  — array of {time, open, high, low, close, volume}
 *   height   — chart height in px (default 480)
 *   markers  — entry/exit signals (wired for PR #3/4, currently unused)
 *   onCrosshairMove — called with (price, time) on crosshair move
 */

import { useEffect, useRef } from "react";

import type { IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { createChart } from "lightweight-charts";

import type { Kline } from "@/lib/useRealtimeKlines";

// ── marker shape ────────────────────────────────────────────────────────────
export interface KlineMarker {
  time: number;
  position: "aboveBar" | "belowBar" | "inBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle" | "square";
  text: string;
}

interface LightweightKlineChartProps {
  candles: Kline[];
  height?: number;
  markers?: KlineMarker[];
  onCrosshairMove?: (price: number, time: number) => void;
}

// ── theme-aware colours ────────────────────────────────────────────────────
function isDark(): boolean {
  return (
    document.documentElement.getAttribute("data-theme") !== "light"
  );
}

function bullColor(): string {
  return isDark() ? "#22c55e" : "#16a34a";
}

function bearColor(): string {
  return isDark() ? "#ef4444" : "#dc2626";
}

function gridColor(): string {
  return isDark()
    ? "rgba(255,240,220,0.05)"
    : "rgba(20,12,12,0.06)";
}

function textColor(): string {
  return isDark()
    ? "rgba(255,240,220,0.42)"
    : "rgba(20,12,12,0.42)";
}

function volumeUpColor(): string {
  return isDark()
    ? "rgba(34,197,94,0.4)"
    : "rgba(22,163,74,0.35)";
}

function volumeDownColor(): string {
  return isDark()
    ? "rgba(239,68,68,0.4)"
    : "rgba(220,38,38,0.35)";
}

function bgColor(): string {
  return isDark()
    ? "#1a1311"
    : "#ffffff";
}

// ── component ──────────────────────────────────────────────────────────────
export function LightweightKlineChart({
  candles,
  height = 480,
  markers = [],
  onCrosshairMove,
}: LightweightKlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const prevCandlesRef = useRef<Kline[]>([]);

  // ── 1. Create chart once ─────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { color: bgColor() },
        textColor: textColor(),
        fontFamily: "Inter, sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: gridColor() },
        horzLines: { color: gridColor() },
      },
      crosshair: {
        vertLine: {
          color: "rgba(255,240,220,0.25)",
          width: 1,
          style: 2, // Dashed
          labelBackgroundColor: isDark() ? "#2b201b" : "#e8e2d4",
        },
        horzLine: {
          color: "rgba(255,240,220,0.25)",
          width: 1,
          style: 2,
          labelBackgroundColor: isDark() ? "#2b201b" : "#e8e2d4",
        },
      },
      rightPriceScale: {
        borderColor: gridColor(),
        textColor: textColor(),
      },
      timeScale: {
        borderColor: gridColor(),
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: bullColor(),
      downColor: bearColor(),
      borderUpColor: bullColor(),
      borderDownColor: bearColor(),
      wickUpColor: bullColor(),
      wickDownColor: bearColor(),
    });
    candleSeriesRef.current = candleSeries;

    // Volume histogram (below price)
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      color: volumeUpColor(),
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    // Crosshair move handler
    if (onCrosshairMove) {
      chart.subscribeCrosshairMove((param) => {
        if (!param.point || !param.time) {
          onCrosshairMove(0, 0);
          return;
        }
        const price = param.seriesData.get(candleSeries);
        if (price && "close" in price) {
          onCrosshairMove(price.close as number, param.time as number);
        }
      });
    }

    // ResizeObserver — only available in real browsers, not jsdom
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          chart.applyOptions({ width: entry.contentRect.width });
        }
      });
      ro.observe(containerRef.current);
      return () => {
        ro.disconnect();
        chart.remove();
        chartRef.current = null;
        candleSeriesRef.current = null;
        volumeSeriesRef.current = null;
      };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height]);

  // ── 2. Feed candle data ───────────────────────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    if (candles === prevCandlesRef.current) return;
    prevCandlesRef.current = candles;

    const candleData = candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const volumeData = candles.map((c) => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? volumeUpColor() : volumeDownColor(),
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);

    // Fit content on first load
    if (chartRef.current && candles.length > 0) {
      chartRef.current.timeScale().fitContent();
    }
  }, [candles]);

  // ── 3. Update markers (PR #3/4 hook — currently empty) ───────────────
  useEffect(() => {
    if (!candleSeriesRef.current) return;
    if (markers.length === 0) return;
    const markerData = markers.map((m) => ({
      time: m.time as Time,
      position: m.position,
      color: m.color,
      shape: m.shape,
      text: m.text,
      id: `marker-${m.time}-${m.text}`,
    }));
    candleSeriesRef.current.setMarkers(markerData);
  }, [markers]);

  return (
    <div
      ref={containerRef}
      className="w-full rounded-2xl overflow-hidden"
      style={{ height }}
    />
  );
}
