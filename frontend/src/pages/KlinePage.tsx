import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { CandlestickChart, RefreshCw } from "lucide-react";
import { Activity } from "lucide-react";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { IndicatorTogglePanel } from "@/components/IndicatorTogglePanel";
import { KlineChart } from "@/components/KlineChart";
import { SymbolPicker } from "@/components/SymbolPicker";
import { TrendAnalysisPanel } from "@/components/TrendAnalysisPanel";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton, SkeletonStatCard } from "@/components/ui/Skeleton";
import { fetchKLines } from "@/lib/api";
import { loadPreferences, savePreferences, type ChartPreferences } from "@/lib/preferences";
import { useKlineStore } from "@/stores/klineStore";
import { useSymbolContext } from "@/stores/symbolContextStore";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export function KlinePage() {
  const { symbol, timeframe, setSymbol, setTimeframe, hydrateFromSearch } = useKlineStore();
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // ── Preferences state ─────────────────────────────────────────────────────
  const [prefs, setPrefs] = useState<ChartPreferences | null>(null);
  const [indicatorPanelOpen, setIndicatorPanelOpen] = useState(false);

  // Load prefs on mount
  useEffect(() => {
    void loadPreferences().then(setPrefs);
  }, []);

  const handleIndicatorToggle = async (indicatorId: string, enabled: boolean) => {
    if (!prefs) return;
    const next: ChartPreferences = {
      ...prefs,
      indicators: {
        ...prefs.indicators,
        [indicatorId]: { ...prefs.indicators[indicatorId], enabled },
      },
    };
    setPrefs(next);
    await savePreferences(next);
  };

  // URL → store: hydrate store from URL searchParams.
  useEffect(() => {
    hydrateFromSearch(searchParams);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Store → URL: after every store change, reflect to URL while preserving other params.
  useEffect(() => {
    const state = useKlineStore.getState();
    const urlSymbol = searchParams.get("symbol");
    const urlTf = searchParams.get("timeframe");
    const nextParams = new URLSearchParams(searchParams);
    if (state.symbol !== urlSymbol) nextParams.set("symbol", state.symbol);
    if (state.timeframe !== urlTf) nextParams.set("timeframe", state.timeframe);
    if (nextParams.toString() !== searchParams.toString()) {
      setSearchParams(nextParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, timeframe]);

  const { data, isLoading, error, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["klines", symbol, timeframe],
    queryFn: () => fetchKLines(symbol, timeframe, 500),
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
    staleTime: 3000,
  });

  // Sync symbol/candles to global symbolContextStore
  useEffect(() => {
    if (!data || data.candles.length === 0) return;
    useSymbolContext.getState().setContext({
      symbol: data.symbol,
      timeframe: data.timeframe,
      candles: data.candles,
    });
  }, [data]);

  // Click outside to close indicator panel
  useEffect(() => {
    if (!indicatorPanelOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Element;
      if (!target.closest("[data-indicator-panel]")) {
        setIndicatorPanelOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [indicatorPanelOpen]);

  // Count how many MA + BOLL indicators are currently enabled
  const maBollCount = prefs
    ? (["ma5", "ma10", "ma20", "ma30", "ma60", "boll"] as const).filter(
        (id) => prefs.indicators[id]?.enabled,
      ).length
    : 0;

  return (
    <div className="flex flex-col gap-5">
      {/* Top bar: symbol picker + indicator toggle */}
      <div className="flex items-center gap-3 relative" data-indicator-panel="container">
        <SymbolPicker
          symbol={symbol}
          timeframe={timeframe}
          onSymbolChange={setSymbol}
          onTimeframeChange={setTimeframe}
        />

        {/* Indicator panel toggle button */}
        <button
          onClick={() => setIndicatorPanelOpen((p) => !p)}
          data-testid="indicator-panel-btn"
          className={cn(
            "h-10 pl-4 pr-4 rounded-full cursor-pointer",
            "flex items-center gap-2",
            "bg-bg-secondary border",
            "text-sm font-medium text-text-secondary",
            "hover:text-text-primary hover:bg-bg-tertiary",
            "border-[rgba(255,240,220,0.08)] hover:border-[rgba(255,240,220,0.16)]",
            "active:scale-[0.98] transition-all",
            indicatorPanelOpen && "border-accent/40 text-text-primary",
          )}
        >
          <Activity className="w-4 h-4" />
          <span>指标</span>
          {maBollCount > 0 && (
            <span
              className={cn(
                "h-5 min-w-[20px] px-1.5 rounded-full text-[10px] font-bold",
                "bg-accent/20 text-accent",
                "inline-flex items-center justify-center leading-none",
              )}
            >
              {maBollCount}
            </span>
          )}
        </button>

        {indicatorPanelOpen && prefs && (
          <div
            className={cn(
              "absolute top-12 left-0 z-50",
              "w-72 rounded-2xl",
              "bg-bg-primary border border-[rgba(255,240,220,0.08)]",
              "shadow-2xl shadow-black/50 overflow-hidden",
              "animate-slide-down",
            )}
            data-indicator-panel="panel"
          >
            <div className="px-4 pt-4 pb-3 border-b border-[rgba(255,240,220,0.06)]">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-text-primary">主图指标</span>
                <span className="text-[11px] text-text-tertiary">
                  {maBollCount}/6 已启用
                </span>
              </div>
            </div>
            <div className="p-3">
              <IndicatorTogglePanel prefs={prefs} onChange={handleIndicatorToggle} />
            </div>
          </div>
        )}
      </div>

      {isLoading && <ChartSkeleton />}

      {error && (
        <ErrorState
          title={t("common.error")}
          description={(error as Error).message || "无法加载 K 线数据，请检查 API 连接"}
          action={
            <Button variant="primary" size="sm" leftIcon={<RefreshCw className="w-3.5 h-3.5" />} onClick={() => void refetch()}>
              {t("common.retry")}
            </Button>
          }
        />
      )}

      {data && data.candles.length > 0 && (
        <>
          <KlineChart
            key={`${data.symbol}-${data.timeframe}-${prefs ? JSON.stringify(prefs.indicators) : "loading"}`}
            candles={data.candles}
            symbol={data.symbol}
            timeframe={data.timeframe}
            dataUpdatedAt={dataUpdatedAt}
          />
          <AnalysisPanel />
          <TrendAnalysisPanel
            candles={data.candles}
            symbol={data.symbol}
            timeframe={data.timeframe}
          />
        </>
      )}

      {data && data.candles.length === 0 && (
        <Card>
          <CardBody className="flex flex-col items-center justify-center text-center py-16 gap-3">
            <div className="w-12 h-12 rounded-2xl bg-bg-tertiary flex items-center justify-center text-text-tertiary">
              <CandlestickChart className="w-5 h-5" />
            </div>
            <p className="text-sm text-text-secondary">{t("common.noData")}</p>
          </CardBody>
        </Card>
      )}

      {isFetching && !isLoading && data && (
        <p className="text-[11px] text-text-tertiary text-center tabular-nums">
          {data.candles.length} {t("kline.candleCount")}
        </p>
      )}
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonStatCard key={i} />
        ))}
      </div>
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden">
        <div className="flex items-end justify-between gap-3 p-5 border-b border-[rgba(255,240,220,0.06)]">
          <Skeleton variant="text" width="120px" height="24px" />
          <Skeleton variant="text" width="80px" height="20px" />
        </div>
        <Skeleton height="480px" className="rounded-none" variant="rectangular" />
      </div>
    </div>
  );
}
