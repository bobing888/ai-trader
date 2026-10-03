/**
 * DashboardPage — 多币种概览首页
 *
 * 替代原 `/` AnalysisPage 作为首页。
 * - 顶部 timeframe 切换器 (1h/4h/1d)
 * - 6 币种 SymbolCard 网格
 * - 5s 自动刷新
 * - 加载 / 错误 / 降级 三态
 *
 * 路由：`/` → DashboardPage;`/analysis` → AnalysisPage (保留旧深度页)
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { SymbolCard } from "@/components/Dashboard/SymbolCard";
import {
  DASHBOARD_DEFAULT_SYMBOLS,
  fetchDashboardOverview,
  type OverviewResponse,
} from "@/lib/dashboardApi";
import { cn } from "@/lib/utils";

const TIMEFRAME_OPTIONS = [
  { value: "1h", label: "1h" },
  { value: "4h", label: "4h" },
  { value: "1d", label: "1d" },
] as const;

type TimeframeOption = (typeof TIMEFRAME_OPTIONS)[number]["value"];

export function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [timeframe, setTimeframe] = useState<TimeframeOption>("4h");

  const { data, isLoading, error, isFetching, dataUpdatedAt } = useQuery<OverviewResponse>({
    queryKey: ["dashboard", "overview", [...DASHBOARD_DEFAULT_SYMBOLS], timeframe],
    queryFn: () => fetchDashboardOverview(DASHBOARD_DEFAULT_SYMBOLS, timeframe),
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
    staleTime: 4_000,
  });

  const handleJump = (symbol: string) => {
    // 跳转单币种深度页（K 线页最合适）
    navigate(`/chart?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`);
  };

  // 渲染骨架
  if (isLoading) {
    return (
      <div className="flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight text-text-primary">
            {t("nav.dashboard")}
          </h1>
          <Skeleton className="h-8 w-48" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <ErrorState
        title={t("common.error")}
        description={error ? (error as Error).message : t("common.noData")}
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* 顶部：标题 + timeframe 切换器 + 数据源 + 时间戳 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col">
          <h1 className="text-2xl font-bold tracking-tight text-text-primary">
            {t("nav.dashboard")}
          </h1>
          <p className="text-xs text-text-tertiary mt-1">
            {data.items.length} 个币种 ·{" "}
            <span className="font-mono">data source: {data.source}</span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* timeframe tabs */}
          <div className="flex items-center gap-1 rounded-full bg-bg-tertiary border border-[rgba(255,240,220,0.06)] p-1">
            {TIMEFRAME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setTimeframe(opt.value)}
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-medium transition-colors",
                  timeframe === opt.value
                    ? "bg-accent text-[#140c0c]"
                    : "text-text-secondary hover:text-text-primary",
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* 数据时间戳 */}
          <span className="text-[10px] text-text-tertiary font-mono tabular-nums hidden md:inline">
            {dataUpdatedAt
              ? `updated ${new Date(dataUpdatedAt).toLocaleTimeString()}`
              : ""}
            {isFetching ? " · syncing" : ""}
          </span>
        </div>
      </div>

      {/* 主区：6 卡片网格 */}
      <Card className="p-4 sm:p-5">
        <div
          className="grid gap-3 sm:gap-4"
          style={{
            gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          }}
        >
          {data.items.map((item) => (
            <SymbolCard key={item.symbol} item={item} onJump={handleJump} />
          ))}
        </div>
      </Card>

      {/* 摘要 footer */}
      <p className="text-[10px] text-text-tertiary text-center tabular-nums">
        {data.items.filter((i) => i.signal).length} 个有效信号 ·{" "}
        {data.items.filter((i) => i.degraded).length} 个降级 · 5s 自动刷新 ·{" "}
        点击卡片跳转 K 线
      </p>
    </div>
  );
}