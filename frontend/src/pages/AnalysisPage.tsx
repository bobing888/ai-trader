/**
 * AnalysisPage — 简化版市场趋势分析。
 *
 * 重构动机：去掉雷达图/指标共振条等细节，改为「结论+理由+操作」三段式直读布局，
 * 并在头部补上当前价作为判断锚点。
 */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { TrendAnalysisPanel } from "@/components/TrendAnalysisPanel";
import { AnalysisHeader } from "@/components/analysis/AnalysisHeader";
import { AnalysisRegimeCard } from "@/components/analysis/AnalysisRegimeCard";
import { Skeleton, SkeletonStatCard } from "@/components/ui/Skeleton";
import { fetchAnalysis, fetchKLines, fetchSymbolMeta } from "@/lib/api";
import { useKlineStore } from "@/stores/klineStore";
import { useSymbolContext } from "@/stores/symbolContextStore";

export function AnalysisPage() {
  const { symbol, timeframe } = useKlineStore();

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["klines", symbol, timeframe],
    queryFn: () => fetchKLines(symbol, timeframe, 500),
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
    staleTime: 3000,
  });

  const { data: ticker } = useQuery({
    queryKey: ["ticker", symbol],
    queryFn: () => fetchSymbolMeta(symbol),
    enabled: !!symbol,
    refetchInterval: 5000,
    staleTime: 4000,
  });

  const { data: analysisData } = useQuery({
    queryKey: ["analysis", symbol, timeframe],
    queryFn: () => fetchAnalysis(symbol, timeframe, 500),
    enabled: !!symbol,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const setContext = useSymbolContext((s) => s.setContext);
  const lastCandle = useMemo(() => {
    if (!data || data.candles.length === 0) return undefined;
    return data.candles[data.candles.length - 1];
  }, [data]);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
        <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden p-6">
          <Skeleton className="h-6 w-48 mb-4" />
          <div className="grid grid-cols-5 gap-px bg-[rgba(255,240,220,0.06)]">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="bg-bg-secondary p-4 min-h-[160px]">
                <Skeleton className="h-4 w-24 mb-3" />
                <Skeleton className="h-8 w-16 mb-2" />
                <Skeleton className="h-3 w-full mb-1" />
                <Skeleton className="h-3 w-3/4" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !data || data.candles.length === 0) {
    return (
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-8 text-center text-text-tertiary text-sm">
        {error ? `数据加载失败：${(error as Error).message}` : "暂无 K 线数据，请检查交易对或网络连接。"}
      </div>
    );
  }

  if (data && lastCandle) {
    setContext({
      symbol: data.symbol,
      timeframe: data.timeframe,
      candles: data.candles,
    });
  }

  return (
    <div className="flex flex-col gap-4 sm:gap-5">
      <AnalysisHeader
        symbol={symbol}
        timeframe={timeframe}
        ticker={ticker}
        klinePrice={lastCandle?.close}
        asOf={analysisData?.as_of}
      />

      {analysisData && <AnalysisRegimeCard data={analysisData} />}

      <TrendAnalysisPanel
        candles={data.candles}
        symbol={data.symbol}
        timeframe={data.timeframe}
        currentPrice={ticker?.price && ticker.price > 0 ? ticker.price : lastCandle?.close}
        change24hPct={ticker?.change_24h}
      />

      {isFetching && (
        <p className="text-[11px] text-text-tertiary text-center tabular-nums">
          {data.candles.length} 根 K 线 · {data.symbol} · {data.timeframe}
        </p>
      )}
    </div>
  );
}
