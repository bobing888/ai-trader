import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { CandlestickChart, RefreshCw } from "lucide-react";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { KlineChart } from "@/components/KlineChart";
import { SymbolPicker } from "@/components/SymbolPicker";
import { TrendAnalysisPanel } from "@/components/TrendAnalysisPanel";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton, SkeletonStatCard } from "@/components/ui/Skeleton";
import { fetchKLines } from "@/lib/api";
import { useKlineStore } from "@/stores/klineStore";
import { useSymbolContext } from "@/stores/symbolContextStore";
import { useTranslation } from "react-i18next";

export function KlinePage() {
  const { symbol, timeframe, setSymbol, setTimeframe, hydrateFromSearch } = useKlineStore();
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // URL → store: hydrate store from URL searchParams.
  useEffect(() => {
    hydrateFromSearch(searchParams);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Store → URL: after every store change, reflect to URL while preserving other params.
  // Read the store synchronously (via getState) to avoid using stale selector values
  // captured during this render commit.
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
    staleTime: 1500,
  });

  // Sync symbol/candles to global symbolContextStore — 让 RightSidebar 的合约计算器能跨页面共享
  useEffect(() => {
    if (!data || data.candles.length === 0) return;
    useSymbolContext.getState().setContext({
      symbol: data.symbol,
      timeframe: data.timeframe,
      candles: data.candles,
    });
  }, [data]);

  // Backup manual poller — react-query's setInterval can be throttled by browser when tab is backgrounded,
  // so we also trigger refetch on a wall-clock interval to guarantee 3s refresh even when hidden.
  useEffect(() => {
    const id = setInterval(() => {
      void refetch();
    }, 3000);
    return () => clearInterval(id);
  }, [refetch]);

  return (
    <div className="flex flex-col gap-5">
      <SymbolPicker
        symbol={symbol}
        timeframe={timeframe}
        onSymbolChange={setSymbol}
        onTimeframeChange={setTimeframe}
      />

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
            key={`${data.symbol}-${data.timeframe}`}
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
          {/* FuturesContractPanel 已搬到全局 RightSidebar（layout/RightSidebar.tsx） */}
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
      {/* KPI strip skeleton */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonStatCard key={i} />
        ))}
      </div>
      {/* Chart skeleton */}
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
