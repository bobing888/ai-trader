/**
 * AnalysisPage — 量化分析 + 市场趋势分析整合页。
 * 替代原 K 线页面：保留 AnalysisPanel + TrendAnalysisPanel，
 * 不含 K 线图（已移除），专注信号与指标解读。
 */

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { TrendAnalysisPanel } from "@/components/TrendAnalysisPanel";
import { Skeleton, SkeletonStatCard } from "@/components/ui/Skeleton";
import { fetchKLines } from "@/lib/api";
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

  // Sync symbol/candles to global symbolContextStore so AnalysisPanel can read it
  const { setContext } = useSymbolContext.getState();
  useEffect(() => {
    if (!data || data.candles.length === 0) return;
    setContext({
      symbol: data.symbol,
      timeframe: data.timeframe,
      candles: data.candles,
    });
  }, [data, setContext]);

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

  return (
    <div className="flex flex-col gap-5">
      {/* 量化分析面板 */}
      <AnalysisPanel />

      {/* 市场趋势分析面板 */}
      <TrendAnalysisPanel
        candles={data.candles}
        symbol={data.symbol}
        timeframe={data.timeframe}
      />

      {/* 数据状态提示 */}
      {isFetching && (
        <p className="text-[11px] text-text-tertiary text-center tabular-nums">
          {data.candles.length} 根 K 线 · {data.symbol} · {data.timeframe}
        </p>
      )}
    </div>
  );
}
