import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { Candle } from "@/lib/api";
import { TIMEFRAMES, type Timeframe } from "@/lib/api";
import {
  COLORS,
  DEFAULT_ENABLED_OVERLAYS,
  OVERLAY_DEFS,
  PANEL_DEFS,
  ALL_DEFS,
  type IndicatorId,
} from "@/lib/indicatorRegistry";
import { SymbolPicker } from "@/components/SymbolPicker";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import {
  adx,
  atr,
  bollingerBands,
  cci,
  ema,
  ichimoku,
  kdj,
  keltnerChannels,
  macd,
  mfi,
  obv,
  rsi,
  sar,
  sma,
  stochastic,
  supertrend,
  vwap,
  williamsR,
} from "@/lib/indicators";
import {
  loadPreferences,
  type ChartPreferences,
} from "@/lib/preferences";

export interface KlineChartProps {
  candles: Candle[];
  symbol: string;
  timeframe: string;
  dataUpdatedAt?: number;
  onSymbolChange?: (symbol: string) => void;
  onTimeframeChange?: (tf: Timeframe) => void;
}

// ── Indicator registry 与配色已移到 @/lib/indicatorRegistry ───────────────────
// 本文件不再持有常量 / 类型 / registry，只保留 React 组件 + KlineChartProps +
// 局部 Crosshair / CandleTooltip interface。
// 这样 Vite Fast Refresh 走 hot module replacement，不会触发 full reload，
// 避免 KlineChart 在 prefs 重 mount 时撞 React StrictMode 双调用导致
// "Rendered more hooks than during the previous render" race。

// ── Crosshair state ─────────────────────────────────────────────────────────

interface Crosshair {
  time?: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  // overlay values (动态）
  [k: string]: number | undefined;
}

export function KlineChart({ candles, symbol, timeframe, onSymbolChange, onTimeframeChange }: KlineChartProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const panelContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const panelChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  // Track last (symbol, timeframe) we called fitContent() for — only refit on actual switch,
  // otherwise periodic refetch would yank the viewport back to full every 3s.
  const lastFitKeyRef = useRef<string>("");
  // 主图 series：id → ISeriesApi（每个 indicator 主线 + extraPlots 子线）
  const seriesRefs = useRef<Record<string, ISeriesApi<"Line" | "Histogram">>>({});
  // 副图 series
  const panelSeriesRefs = useRef<Record<string, ISeriesApi<"Line" | "Histogram">>>({});
  // 同步 candles 到 ref，让 dblclick handler（订阅 chart 时 closure 捕获不到 props 更新）能读到最新值
  const candlesRef = useRef<Candle[]>([]);
  useEffect(() => { candlesRef.current = candles; }, [candles]);

  // 把"最新一根 K 线"放到视图正中央 — 视野左右各留 ~50 根的空间，更方便看趋势结构
  const centerLatestCandle = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const candlesLen = candlesRef.current.length;
    if (candlesLen === 0) return;
    const lastIndex = candlesLen - 1;
    try {
      // 用 setVisibleLogicalRange 直接定位：最新一根落在 (from+to)/2
      // from = lastIndex - half, to = lastIndex + half，使 N = 2*half 根 K 线居中
      const half = 50;
      chart.timeScale().setVisibleLogicalRange({
        from: lastIndex - half,
        to: lastIndex + half,
      });
    } catch {
      try { chart.timeScale().fitContent(); } catch {}
    }
  }, []);

  // Subscription tracking for proper cleanup
  const mainTimeRangeHandlerRef = useRef<((range: any) => void) | null>(null);
  const panelTimeRangeHandlerRef = useRef<((range: any) => void) | null>(null);
  const mainCrosshairHandlerRef = useRef<((param: any) => void) | null>(null);
  const panelCrosshairHandlerRef = useRef<((param: any) => void) | null>(null);
  const mainAliveRef = useRef<boolean>(true);
  const panelAliveRef = useRef<boolean>(true);

  // ── Preferences (loaded from backend + localStorage fallback) ──
  const [prefs, setPrefs] = useState<ChartPreferences | null>(null);
  // safety: lightweight-charts v5 setData 在传入非数组或非预期类型时会抛 "t.map is not a function"
  // 这里统一做一次校验，确保传出去的永远是数组（或空）
  const safeSetData = useCallback((ref: any, data: unknown): void => {
    if (!ref) return;
    try {
      ref.setData(Array.isArray(data) ? data : []);
    } catch (e) {
      console.warn("[KlineChart] setData 失败，已忽略:", e, "data type:", typeof data, "isArray:", Array.isArray(data));
    }
  }, []);
  const enabledIndicators = useMemo(
    () => new Set(ALL_DEFS.filter((d) => prefs?.indicators[d.id]?.enabled).map((d) => d.id)),
    [prefs],
  );

  const [crosshair, setCrosshair] = useState<Crosshair>({});
  const [tooltip, setTooltip] = useState<null | {
    time: number; open: number; high: number; low: number; close: number; x: number; y: number;
  }>(null);

  const hasPanel = useMemo(
    () => PANEL_DEFS.some((i) => enabledIndicators.has(i.id)),
    [enabledIndicators],
  );

  const closes = useMemo(() => candles.map((c) => c.close), [candles]);

  // ── Compute all indicators (single pass through candles) ──
  const computed = useMemo(() => {
    const toSeries = (arr: number[]): LineData<Time>[] =>
      arr
        .map((v, i) => ({ time: candles[i].time as UTCTimestamp, value: v }))
        .filter((p) => Number.isFinite(p.value));

    const out: Record<string, any> = {};

    // MA 多周期
    ([5, 10, 20, 30, 60] as const).forEach((n) => {
      out[`ma${n}`] = toSeries(sma(closes, n));
    });
    // EMA
    ([12, 26, 50] as const).forEach((n) => {
      out[`ema${n}`] = toSeries(ema(closes, n));
    });
    // BOLL
    const boll = bollingerBands(closes, 20, 2);
    out.boll = {
      upper: toSeries(boll.upper),
      middle: toSeries(boll.middle),
      lower: toSeries(boll.lower),
    };
    // VWAP
    out.vwap = toSeries(vwap(candles, 24));
    // SAR
    const sarRes = sar(candles);
    out.sar = {
      trend: sarRes.trend,
      value: sarRes.value.map((v, i) => ({ time: candles[i].time as UTCTimestamp, value: v })).filter((p) => Number.isFinite(p.value)),
    };
    // Supertrend
    const stRes = supertrend(candles);
    out.supertrend = {
      trend: stRes.trend,
      value: stRes.value.map((v, i) => ({ time: candles[i].time as UTCTimestamp, value: v })).filter((p) => Number.isFinite(p.value)),
    };
    // Keltner
    const kc = keltnerChannels(candles);
    out.keltner = {
      upper: toSeries(kc.upper),
      middle: toSeries(kc.middle),
      lower: toSeries(kc.lower),
    };
    // Ichimoku
    const ic = ichimoku(candles);
    out.ichimoku = {
      tenkan: toSeries(ic.tenkan),
      kijun: toSeries(ic.kijun),
      senkouA: toSeries(ic.senkouA),
      senkouB: toSeries(ic.senkouB),
      chikou: toSeries(ic.chikou),
    };

    // 副图指标
    out.rsi = toSeries(rsi(closes, 14));
    out.rsi6 = toSeries(rsi(closes, 6));
    out.rsi24 = toSeries(rsi(closes, 24));
    const m = macd(closes);
    out.macd = {
      macd: toSeries(m.macd),
      signal: toSeries(m.signal),
      histogram: m.histogram.map((v, i) => ({
        time: candles[i].time as UTCTimestamp,
        value: v,
        color: v >= 0 ? "rgba(34, 197, 94, 0.6)" : "rgba(239, 68, 68, 0.6)",
      })),
    };
    const kd = kdj(candles);
    out.kdj = {
      k: toSeries(kd.k),
      d: toSeries(kd.d),
      j: toSeries(kd.j),
    };
    out.obv = toSeries(obv(candles));
    const stochR = stochastic(candles, 14, 3);
    out.stoch = {
      k: toSeries(stochR.k),
      d: toSeries(stochR.d),
    };
    out.cci = toSeries(cci(candles, 20));
    out.wr = toSeries(williamsR(candles, 14));
    out.mfi = toSeries(mfi(candles, 14));
    const adxR = adx(candles, 14);
    out.adx = {
      adx: toSeries(adxR.adx),
      pdi: toSeries(adxR.pdi),
      ndi: toSeries(adxR.ndi),
    };
    out.atr = toSeries(atr(candles, 14));

    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closes, candles]);

  // ── Load preferences on mount ──
  useEffect(() => {
    let cancelled = false;
    void loadPreferences().then((p) => {
      if (!cancelled) setPrefs(p);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const latest = useMemo(() => {
    if (candles.length === 0) return null;
    const last = candles[candles.length - 1];
    return { last };
  }, [candles]);

  const volumeAvg = useMemo(() => {
    if (candles.length === 0) return 0;
    return candles.reduce((s, c) => s + c.volume, 0) / candles.length;
  }, [candles]);

  // ── Main chart init ──
  useEffect(() => {
    if (!prefs) return;
    if (!containerRef.current) return;
    mainAliveRef.current = true;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: COLORS.bg },
        textColor: COLORS.textSecondary,
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: COLORS.grid, style: 1 },
        horzLines: { color: COLORS.grid, style: 1 },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: COLORS.border,
      },
      rightPriceScale: {
        borderColor: COLORS.border,
        scaleMargins: { top: 0.08, bottom: 0.18 },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: "rgba(204, 255, 0, 0.3)", width: 1, style: 2,
          labelVisible: false, labelBackgroundColor: "#ccff00",
        },
        horzLine: {
          color: "rgba(204, 255, 0, 0.3)", width: 1, style: 2,
          labelVisible: false, labelBackgroundColor: "#ccff00",
        },
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.bull, downColor: COLORS.bear,
      borderUpColor: COLORS.bull, borderDownColor: COLORS.bear,
      wickUpColor: COLORS.bull, wickDownColor: COLORS.bear,
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });

    // 为每个 overlay indicator 预创建 series（主 + extraPlots）
    // 关键视觉调优：lineWidth 必须 ≥ 2 否则在密集 K 线上肉眼几乎看不见
    // MA / EMA / VWAP / SAR / Supertrend = 2px
    // BOLL 中轨 = 3px（视觉锚，最粗）；BOLL 上下轨 = 1px（辅助）
    for (const def of OVERLAY_DEFS) {
      const isBollMain = def.id === "boll";
      seriesRefs.current[def.id] = chart.addSeries(LineSeries, {
        color: def.color,
        lineWidth: isBollMain ? 3 : 2,
        lineStyle: 0,
        priceLineVisible: false,
        // 主指标（默认开启）显示当前值标签；其它隐藏
        lastValueVisible: !!DEFAULT_ENABLED_OVERLAYS.has(def.id),
        crosshairMarkerVisible: false,
      });
      if (def.extraPlots) {
        for (const ep of def.extraPlots) {
          const seriesId = `${def.id}_${ep.id}`;
          const isCloud = def.id === "ichimoku" && (ep.id === "spanA" || ep.id === "spanB");
          const isUpperOrLower = ep.id === "upper" || ep.id === "lower";
          seriesRefs.current[seriesId] = chart.addSeries(LineSeries, {
            color: ep.color,
            lineWidth: isUpperOrLower ? 1 : 2,  // 上/下轨 1px 辅助；Ichimoku span 2px
            lineStyle: isCloud ? 0 : 0,
            priceLineVisible: false,
            lastValueVisible: !!DEFAULT_ENABLED_OVERLAYS.has(def.id),
            crosshairMarkerVisible: false,
          });
        }
      }
    }

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // First-paint fix: prefs are loaded async, so by the time chart is created the
    // candle/volume effect (deps: [candles, ...]) may have already fired with null refs.
    // Push the current candles once here to guarantee the user sees red/green bars
    // immediately, instead of waiting for the next 3s refetch.
    if (candles.length > 0) {
      const firstPaintCandles = candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open, high: c.high, low: c.low, close: c.close,
      }));
      const firstPaintVolume = candles.map((c) => {
        const bullish = c.close >= c.open;
        const isHigh = c.volume > volumeAvg * 1.5;
        const baseAlpha = isHigh ? 0.85 : 0.32;
        return {
          time: c.time as UTCTimestamp,
          value: c.volume,
          color: bullish ? `rgba(34, 197, 94, ${baseAlpha})` : `rgba(239, 68, 68, ${baseAlpha})`,
        };
      });
      safeSetData(candleSeries, firstPaintCandles);
      safeSetData(volumeSeries, firstPaintVolume);
      try { candleSeries.priceScale().applyOptions({ autoScale: true }); } catch {}
      try { chart.timeScale().fitContent(); } catch {}
      centerLatestCandle();
      requestAnimationFrame(() => {
        try { chart.timeScale().fitContent(); } catch {}
        centerLatestCandle();
      });
      lastFitKeyRef.current = `${symbol}-${timeframe}`;
    }

    // subscribeClick 自实现 dblclick 检测：350ms 内连续两次 click 视为双击
    // 这样不依赖 DOM dblclick 事件，避免 crosshair 拖动冲突
    const dblClickRef = { lastTime: 0, lastX: 0, lastY: 0 };
    const clickHandler = (param: any) => {
      if (!param.point) return;
      const now = performance.now();
      const dx = param.point.x - dblClickRef.lastX;
      const dy = param.point.y - dblClickRef.lastY;
      const dist = Math.hypot(dx, dy);
      const dt = now - dblClickRef.lastTime;
      const isDouble = dt < 350 && dist < 8 && dblClickRef.lastTime > 0;
      dblClickRef.lastTime = now;
      dblClickRef.lastX = param.point.x;
      dblClickRef.lastY = param.point.y;
      if (!isDouble) return;
      const candlesLen = candlesRef.current.length;
      if (candlesLen === 0) return;
      // 双击：把"最近 K 线（最后一根）"放到视图正中央
      centerLatestCandle();
      try { candleSeries.priceScale().applyOptions({ autoScale: true }); } catch {}
    };
    chart.subscribeClick(clickHandler);

    return () => {
      mainAliveRef.current = false;
      if (chartRef.current) {
        try {
          if (mainTimeRangeHandlerRef.current) {
            chartRef.current.timeScale().unsubscribeVisibleTimeRangeChange(mainTimeRangeHandlerRef.current);
            mainTimeRangeHandlerRef.current = null;
          }
          if (mainCrosshairHandlerRef.current) {
            chartRef.current.unsubscribeCrosshairMove(mainCrosshairHandlerRef.current);
            mainCrosshairHandlerRef.current = null;
          }
        } catch {
          /* chart disposed */
        }
      }
      try { chart.remove(); } catch {}
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      seriesRefs.current = {};
    };
  }, [prefs]);

  // ── Panel chart init ──
  useEffect(() => {
    if (!prefs) return;
    if (!panelContainerRef.current) return;
    panelAliveRef.current = true;
    const panel = createChart(panelContainerRef.current, {
      autoSize: true,
      layout: {
        background: { color: COLORS.bg },
        textColor: COLORS.textSecondary,
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: COLORS.grid, style: 1 },
        horzLines: { color: COLORS.grid, style: 1 },
      },
      timeScale: {
        timeVisible: true, secondsVisible: false, borderColor: COLORS.border,
      },
      rightPriceScale: { borderColor: COLORS.border },
      crosshair: {
        mode: 1,
        vertLine: {
          color: "rgba(204, 255, 0, 0.3)", width: 1, style: 2,
          labelVisible: false, labelBackgroundColor: "#ccff00",
        },
        horzLine: {
          color: "rgba(204, 255, 0, 0.3)", width: 1, style: 2,
          labelVisible: false, labelBackgroundColor: "#ccff00",
        },
      },
    });

    // 副图 series（只创建用户当前启用的 + 总是创建以备切换）
    for (const def of PANEL_DEFS) {
      if (def.id === "macd" || def.id === "kdj" || def.id === "stoch" || def.id === "adx") {
        // MACD: macd 线 + signal 线 + histogram 柱
        // KDJ: K + D + J
        // Stoch: K + D
        // ADX: adx + pdi + ndi
        if (def.id === "macd") {
          panelSeriesRefs.current.macd = panel.addSeries(LineSeries, { color: COLORS.macd, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
          panelSeriesRefs.current.macd_signal = panel.addSeries(LineSeries, { color: COLORS.macdSignal, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
          panelSeriesRefs.current.macdHist = panel.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false });
        } else if (def.id === "kdj") {
          panelSeriesRefs.current.kdj = panel.addSeries(LineSeries, { color: COLORS.kdjK, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
          panelSeriesRefs.current.kdj_d = panel.addSeries(LineSeries, { color: COLORS.kdjD, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
          panelSeriesRefs.current.kdj_j = panel.addSeries(LineSeries, { color: COLORS.kdjJ, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        } else if (def.id === "stoch") {
          panelSeriesRefs.current.stoch = panel.addSeries(LineSeries, { color: COLORS.stochK, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
          panelSeriesRefs.current.stoch_d = panel.addSeries(LineSeries, { color: COLORS.stochD, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        } else if (def.id === "adx") {
          panelSeriesRefs.current.adx = panel.addSeries(LineSeries, { color: COLORS.adx, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
          panelSeriesRefs.current.adx_pdi = panel.addSeries(LineSeries, { color: COLORS.pdi, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
          panelSeriesRefs.current.adx_ndi = panel.addSeries(LineSeries, { color: COLORS.ndi, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        }
      } else {
        panelSeriesRefs.current[def.id] = panel.addSeries(LineSeries, {
          color: def.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
      }
    }

    panelChartRef.current = panel;

    // 主副图 time scale 同步
    const mainHandler = (range: any) => {
      if (!mainAliveRef.current || !panelAliveRef.current) return;
      try {
        if (range && panelChartRef.current) panelChartRef.current.timeScale().setVisibleRange(range);
      } catch {
        /* chart disposed */
      }
    };
    const panelHandler = (range: any) => {
      if (!mainAliveRef.current || !panelAliveRef.current) return;
      try {
        if (range && chartRef.current) chartRef.current.timeScale().setVisibleRange(range);
      } catch {
        /* chart disposed */
      }
    };
    mainTimeRangeHandlerRef.current = mainHandler;
    panelTimeRangeHandlerRef.current = panelHandler;
    if (chartRef.current) {
      chartRef.current.timeScale().subscribeVisibleTimeRangeChange(mainHandler);
      panel.timeScale().subscribeVisibleTimeRangeChange(panelHandler);
    }

    // 副图 crosshair（统一更新到主 crosshair state）
    const panelCrosshair = () => {
      if (!mainAliveRef.current || !panelAliveRef.current) return;
      // 不从副图直接 setCrosshair（主图已 set，副图 crosshair 会触发主图 handler → set）
    };
    panelCrosshairHandlerRef.current = panelCrosshair;
    panel.subscribeCrosshairMove(panelCrosshair);

    return () => {
      panelAliveRef.current = false;
      try { panel.timeScale().unsubscribeVisibleTimeRangeChange(panelTimeRangeHandlerRef.current!); } catch {}
      panelTimeRangeHandlerRef.current = null;
      try { panel.unsubscribeCrosshairMove(panelCrosshairHandlerRef.current!); } catch {}
      panelCrosshairHandlerRef.current = null;
      try { chartRef.current?.timeScale().unsubscribeVisibleTimeRangeChange(mainTimeRangeHandlerRef.current!); } catch {}
      mainTimeRangeHandlerRef.current = null;
      try { panel.remove(); } catch {}
      panelChartRef.current = null;
      panelSeriesRefs.current = {};
    };
  }, [prefs]);

  // ── Main chart candle/volume data ──
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || candles.length === 0) return;
    const candleData: CandlestickData<Time>[] = candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    const volumeData: HistogramData<Time>[] = candles.map((c) => {
      const bullish = c.close >= c.open;
      const isHigh = c.volume > volumeAvg * 1.5;
      const baseAlpha = isHigh ? 0.85 : 0.32;
      return {
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: bullish ? `rgba(34, 197, 94, ${baseAlpha})` : `rgba(239, 68, 68, ${baseAlpha})`,
      };
    });
    safeSetData(candleSeriesRef.current, candleData);
    safeSetData(volumeSeriesRef.current, volumeData);
    // v5 lightweight-charts bug: 用户在 chart 上 zoom 过 price scale 后，
    // autoscaling 被禁用，后续 setData 不会重置 → candles 看不见（v4 fix 已合并但 v5 仍未默认开启）。
    // 这里强制恢复 autoscaling，确保每次 update 都 fit 到 candles 范围。
    try {
      candleSeriesRef.current.priceScale().applyOptions({ autoScale: true });
    } catch {}
    const fitKey = `${symbol}-${timeframe}`;
    if (lastFitKeyRef.current !== fitKey) {
      // 首屏：把"最近 K 线"放到视图正中央（而不是默认 fitContent 把它丢到最右边）
      // 用户分析趋势需要看到过去 ~50 根 + 未来 ~50 根（右边留白）— 居中视野更容易观察形态
      try { chartRef.current?.timeScale().fitContent(); } catch {}
      centerLatestCandle();
      requestAnimationFrame(() => {
        try {
          chartRef.current?.timeScale().fitContent();
          centerLatestCandle();
        } catch {}
      });
      lastFitKeyRef.current = fitKey;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, volumeAvg, computed, symbol, timeframe]);

// ── Sync overlay indicator data ──
  useEffect(() => {
    if (!prefs) return;
    const setLineOrClear = (key: string, data: any[] | undefined) => {
      const ref = seriesRefs.current[key];
      if (!ref) return;
      const enabled = enabledIndicators.has(key as IndicatorId) ||
        // 子图（boll_upper 等）跟随主指标
        (() => {
          const mainKey = key.split("_")[0];
          return enabledIndicators.has(mainKey as IndicatorId);
        })();
      safeSetData(ref, enabled && data ? data : []);
    };
    // MA / EMA / VWAP 单线
    (["ma5", "ma10", "ma20", "ma30", "ma60", "ema12", "ema26", "ema50", "vwap"] as const).forEach((id) => {
      setLineOrClear(id, (computed as any)[id] as LineData<Time>[]);
    });
    // BOLL 3 线
    setLineOrClear("boll", (computed as any).boll?.middle);
    setLineOrClear("boll_upper", (computed as any).boll?.upper);
    setLineOrClear("boll_lower", (computed as any).boll?.lower);
    // SAR / Supertrend（主线）
    setLineOrClear("sar", (computed as any).sar?.value);
    setLineOrClear("supertrend", (computed as any).supertrend?.value);
    // Keltner 3 线
    setLineOrClear("keltner", (computed as any).keltner?.middle);
    setLineOrClear("keltner_upper", (computed as any).keltner?.upper);
    setLineOrClear("keltner_lower", (computed as any).keltner?.lower);
    // Ichimoku
    setLineOrClear("ichimoku", (computed as any).ichimoku?.tenkan);
    setLineOrClear("ichimoku_kijun", (computed as any).ichimoku?.kijun);
    setLineOrClear("ichimoku_spanA", (computed as any).ichimoku?.senkouA);
    setLineOrClear("ichimoku_spanB", (computed as any).ichimoku?.senkouB);
  }, [prefs, enabledIndicators, computed]);

  // ── Sync panel indicator data ──
  useEffect(() => {
    if (!prefs) return;
    const setLineOrClear = (key: string, data: any[] | undefined) => {
      const ref = panelSeriesRefs.current[key];
      if (!ref) return;
      const enabled = enabledIndicators.has(key as IndicatorId) ||
        (() => {
          const mainKey = key.split("_")[0];
          return enabledIndicators.has(mainKey as IndicatorId);
        })();
      safeSetData(ref, enabled && data ? data : []);
    };
    // 单线副图
    (["rsi", "rsi6", "rsi24", "obv", "stoch", "cci", "wr", "mfi", "atr"] as const).forEach((id) => {
      setLineOrClear(id, (computed as any)[id] as LineData<Time>[]);
    });
    // MACD：line + signal + histogram
    setLineOrClear("macd", (computed as any).macd?.macd);
    setLineOrClear("macd_signal", (computed as any).macd?.signal);
    setLineOrClear("macdHist", (computed as any).macd?.histogram);
    // KDJ：K + D + J
    setLineOrClear("kdj", (computed as any).kdj?.k);
    setLineOrClear("kdj_d", (computed as any).kdj?.d);
    setLineOrClear("kdj_j", (computed as any).kdj?.j);
    // Stoch: K + D
    setLineOrClear("stoch", (computed as any).stoch?.k);
    setLineOrClear("stoch_d", (computed as any).stoch?.d);
    // ADX: adx + pdi + ndi
    setLineOrClear("adx", (computed as any).adx?.adx);
    setLineOrClear("adx_pdi", (computed as any).adx?.pdi);
    setLineOrClear("adx_ndi", (computed as any).adx?.ndi);
  }, [prefs, enabledIndicators, computed]);

  // ── Main crosshair handler ──
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current) return;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current!;

    const mainCrosshairHandler = (param: any) => {
      if (!mainAliveRef.current || !panelAliveRef.current) return;
      if (!param.time || !param.seriesData) {
        setCrosshair({});
        setTooltip(null);
        return;
      }
      const candle = param.seriesData.get(candleSeries) as CandlestickData<Time> | undefined;
      const volume = param.seriesData.get(volumeSeries) as HistogramData<Time> | undefined;
      const values: Crosshair = {
        time: typeof param.time === "number" ? param.time : Number(param.time),
        open: candle?.open, high: candle?.high, low: candle?.low, close: candle?.close,
        volume: volume?.value,
      };
      // 收集所有启用的 overlay 的当前值
      for (const def of OVERLAY_DEFS) {
        if (!enabledIndicators.has(def.id)) continue;
        const s = seriesRefs.current[def.id];
        if (s) {
          const v = param.seriesData.get(s) as LineData<Time> | undefined;
          if (v) values[def.id] = v.value;
        }
        if (def.extraPlots) {
          for (const ep of def.extraPlots) {
            const s2 = seriesRefs.current[`${def.id}_${ep.id}`];
            if (s2) {
              const v2 = param.seriesData.get(s2) as LineData<Time> | undefined;
              if (v2) values[`${def.id}_${ep.id}`] = v2.value;
            }
          }
        }
      }
      setCrosshair(values);
      // 浮动 tooltip 同步：仅在主图有效区显示
      if (candle && param.point && typeof param.point.x === "number" && typeof param.point.y === "number") {
        const x = typeof param.point.x === "number" ? param.point.x : Number((param.point as any).x);
        const y = typeof param.point.y === "number" ? param.point.y : Number((param.point as any).y);
        setTooltip({
          time: values.time ?? Number(param.time),
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
          x,
          y,
        });
      } else {
        setTooltip(null);
      }
    };
    mainCrosshairHandlerRef.current = mainCrosshairHandler;
    chartRef.current.subscribeCrosshairMove(mainCrosshairHandler);
    return () => {
      if (chartRef.current && mainCrosshairHandlerRef.current) {
        try { chartRef.current.unsubscribeCrosshairMove(mainCrosshairHandlerRef.current); } catch {}
        mainCrosshairHandlerRef.current = null;
      }
    };
  }, [enabledIndicators]);

  // 24h 涨跌走 ticker（避免用区间涨跌混淆）
  const displayTime = crosshair.time ?? latest?.last.time;
  const isLive = !crosshair.time;

  if (!prefs) {
    // 加载中
    return (
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-8 text-center text-text-tertiary text-sm">
        加载指标配置…
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden">
      {/* Top bar: Symbol + Timeframe pills (右上角，与 crosshair bar 同行 — 一目了然) */}
      <div
        className="relative flex items-center gap-3 px-5 border-b border-[rgba(255,240,220,0.06)] bg-bg-tertiary/30"
        style={{ minHeight: "48px" }}
      >
        {/* Spacer pushes symbol + timeframe pills to the right (用户要求右上角、紧贴 1 分旁边) */}
        <div className="flex-1" />
        {onSymbolChange && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-text-tertiary">交易对</span>
            <SymbolPicker
              symbol={symbol}
              timeframe={timeframe as Timeframe}
              onSymbolChange={onSymbolChange}
              // onTimeframeChange 不传 — KlineChart 顶部右侧单独渲染 timeframe pills
            />
          </div>
        )}
        {onTimeframeChange && (
          <div className="flex items-center gap-1 p-1 rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.06)]">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange(tf)}
                data-testid={`tf-${tf}`}
                className={cn(
                  "h-7 px-2.5 text-[11px] font-medium rounded-full transition-all duration-150",
                  "active:scale-[0.95]",
                  timeframe === tf
                    ? "bg-accent text-[#140c0c] shadow-[0_0_0_1px_rgba(204,255,0,0.3)]"
                    : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary",
                )}
              >
                {t(`timeframes.${tf}`)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Crosshair values bar — hover K 线时显示当前 bar 的指标快照 */}
      <div
        className="relative flex items-center flex-nowrap gap-x-4 px-5 border-b border-[rgba(255,240,220,0.06)] bg-bg-tertiary/30 overflow-x-auto"
        style={{ height: "32px" }}
      >
        {/* 主图指标值（按 enabled 顺序） */}
        {OVERLAY_DEFS.filter((d) => enabledIndicators.has(d.id)).map((d) => {
          const v = crosshair[d.id];
          return (
            <CrosshairValue key={d.id} label={d.label} value={v} color={d.color} digits={2} />
          );
        })}
        {/* 副图指标值 */}
        {PANEL_DEFS.filter((d) => enabledIndicators.has(d.id)).map((d) => {
          const v = crosshair[d.id];
          const digits = d.id === "macd" ? 3 : d.id === "wr" || d.id === "rsi" || d.id === "rsi6" || d.id === "rsi24" || d.id === "mfi" ? 1 : 2;
          return (
            <CrosshairValue key={d.id} label={d.label} value={v} color={d.color} digits={digits} />
          );
        })}
        {/* Timestamp pinned to top-right */}
        <span
          className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-text-tertiary tabular-nums whitespace-nowrap pointer-events-none"
          style={{ minWidth: "150px", textAlign: "right" }}
        >
          {!isLive && displayTime
            ? new Date(displayTime * 1000).toLocaleString("zh-CN", { hour12: false })
            : "\u00A0"}
        </span>
      </div>

      {/* Main chart — 浮动 tooltip overlay 跟随 crosshair */}
      <div className="relative">
        <div ref={containerRef} className="w-full bg-bg-secondary" style={{ height: "440px" }} data-testid="kline-chart" />
        {tooltip && (
          <CandleTooltip
            time={tooltip.time}
            open={tooltip.open}
            high={tooltip.high}
            low={tooltip.low}
            close={tooltip.close}
            x={tooltip.x}
            y={tooltip.y}
            containerWidth={containerRef.current?.clientWidth ?? 0}
            containerHeight={440}
          />
        )}
      </div>
      {/* Panel chart */}
      {hasPanel && (
        <div ref={panelContainerRef} className="w-full bg-bg-secondary border-t border-[rgba(255,240,220,0.06)]" style={{ height: "180px" }} />
      )}
    </div>
  );
}

interface CandleTooltipProps {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  x: number;
  y: number;
  containerWidth: number;
  containerHeight: number;
}

function CandleTooltip({ time, open, high, low, close, x, y, containerWidth, containerHeight }: CandleTooltipProps) {
  // 防止 tooltip 越界：距右/下边界 8px 内就反向偏移
  const TOOLTIP_W = 200;
  const TOOLTIP_H = 132;
  const MARGIN = 8;
  const left = Math.min(Math.max(x + 14, MARGIN), Math.max(containerWidth - TOOLTIP_W - MARGIN, MARGIN));
  const top = (y + 14 + TOOLTIP_H > containerHeight - MARGIN)
    ? Math.max(y - TOOLTIP_H - 14, MARGIN)
    : y + 14;
  const positive = close >= open;
  return (
    <div
      className="absolute z-30 pointer-events-none rounded-lg shadow-2xl border border-[rgba(255,240,220,0.12)] bg-bg-primary/95 backdrop-blur-sm p-2.5 text-[11px] tabular-nums"
      style={{ left, top, width: TOOLTIP_W }}
    >
      <div className="text-text-tertiary mb-1.5 text-[10px] tracking-wider uppercase">
        {new Date(time * 1000).toLocaleString("zh-CN", { hour12: false })}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        <span className="text-text-tertiary">开</span>
        <span className="text-text-primary font-medium text-right">{open.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        <span className="text-text-tertiary">高</span>
        <span className="text-bull font-medium text-right">{high.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        <span className="text-text-tertiary">低</span>
        <span className="text-bear font-medium text-right">{low.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        <span className="text-text-tertiary">收</span>
        <span className={`font-medium text-right ${positive ? "text-bull" : "text-bear"}`}>
          {close.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          <span className="ml-1.5 text-[10px]">
            ({positive ? "+" : ""}
            {(((close - open) / open) * 100).toFixed(2)}%)
          </span>
        </span>
      </div>
    </div>
  );
}

function CrosshairValue({ label, value, color, digits = 2 }: { label: string; value: number | undefined; color: string; digits?: number }) {
  return (
    <span className="text-[11px] tabular-nums whitespace-nowrap" style={{ color }}>
      {label} <span className="text-text-primary font-medium">{value !== undefined ? value.toFixed(digits) : "—"}</span>
    </span>
  );
}
