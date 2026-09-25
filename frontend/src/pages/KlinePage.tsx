import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { CandlestickChart, RefreshCw } from "lucide-react";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { IndicatorTogglePanel } from "@/components/IndicatorTogglePanel";
import { KlineChart } from "@/components/KlineChart";
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

export function KlinePage() {
  const { symbol, timeframe, setSymbol, setTimeframe, hydrateFromSearch } = useKlineStore();
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // ── Preferences state ─────────────────────────────────────────────────────
  const [prefs, setPrefs] = useState<ChartPreferences | null>(null);

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

  // Backup manual poller
  useEffect(() => {
    const id = setInterval(() => {
      void refetch();
    }, 3000);
    return () => clearInterval(id);
  }, [refetch]);

  return (
    <div className="flex flex-col gap-5">
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
            onSymbolChange={setSymbol}
            onTimeframeChange={setTimeframe}
          />

          {/* Indicator toolbar — 永远展开在 K 线图正上方，方便一键切换 */}
          {prefs && (
            <Card className="p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold text-text-primary">主图指标</span>
                <span className="text-[11px] text-text-tertiary">
                  MA 系列 + BOLL，点击切换显示/隐藏
                </span>
              </div>
              <IndicatorTogglePanel prefs={prefs} onChange={handleIndicatorToggle} />
            </Card>
          )}

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
