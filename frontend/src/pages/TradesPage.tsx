import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  TrendingUp,
  TrendingDown,
  Receipt,
  Target,
  BarChart3,
  Clock,
  Tag,
  Hash,
  DollarSign,
  Layers,
  Search,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Drawer } from "@/components/ui/Drawer";
import { EmptyState } from "@/components/ui/EmptyState";
import { EquityPanel } from "@/components/EquityPanel";
import { SkeletonStatCard, SkeletonTable } from "@/components/ui/Skeleton";
import { StatCard } from "@/components/ui/StatCard";
import type { Trade } from "@/lib/api";
import { fetchTrades, fetchTradesSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

export function TradesPage() {
  const { t } = useTranslation();
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [search, setSearch] = useState("");

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["trades-summary"],
    queryFn: fetchTradesSummary,
  });

  const { data: tradesData, isLoading: tradesLoading } = useQuery({
    queryKey: ["trades", 50],
    queryFn: () => fetchTrades({ limit: 50 }),
  });

  const profitTone = summary
    ? summary.total_profit_abs > 0
      ? "bull"
      : summary.total_profit_abs < 0
        ? "bear"
        : "neutral"
    : "neutral";

  // Client-side filter on pair / strategy / enter_tag
  const filteredTrades = useMemo(() => {
    if (!tradesData) return [];
    const q = search.trim().toLowerCase();
    if (!q) return tradesData.trades;
    return tradesData.trades.filter((trade) => {
      return (
        trade.pair.toLowerCase().includes(q) ||
        (trade.strategy ?? "").toLowerCase().includes(q) ||
        (trade.enter_tag ?? "").toLowerCase().includes(q)
      );
    });
  }, [tradesData, search]);

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            {t("trade.title")}
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            {tradesData
              ? `${tradesData.total_count} 笔成交 · 数据源 ${tradesData.source}`
              : t("common.loading")}
          </p>
        </div>

        {/* Inline search */}
        <div className="relative w-full sm:w-auto sm:min-w-[260px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索币种 / 策略…"
            className={cn(
              "w-full h-9 pl-9 pr-9 rounded-full",
              "bg-bg-secondary border border-[rgba(255,240,220,0.06)]",
              "text-sm text-text-primary placeholder:text-text-tertiary",
              "focus:outline-none focus:border-accent/40 focus:bg-bg-tertiary",
              "transition-colors",
            )}
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-full text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
              aria-label="Clear search"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Stat cards */}
      {summaryLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            label={t("trade.title")}
            numericValue={summary?.total_trades ?? 0}
            format={(v) => Math.round(v).toString()}
            icon={<Receipt className="w-4 h-4" />}
          />
          <StatCard
            label={t("backtest.winRate")}
            numericValue={summary?.win_rate ?? 0}
            format={(v) => `${v.toFixed(1)}%`}
            icon={<Target className="w-4 h-4" />}
          />
          <StatCard
            label="净盈亏"
            numericValue={summary?.total_profit_abs ?? 0}
            format={(v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}`}
            tone={profitTone}
            icon={summary?.total_profit_abs && summary.total_profit_abs >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          />
          <StatCard
            label="盈亏比"
            numericValue={summary?.profit_factor ?? 0}
            format={(v) => v.toFixed(2)}
            icon={<BarChart3 className="w-4 h-4" />}
          />
        </div>
      )}

      {/* Result count strip (visible when filtering) */}
      {search && (
        <div className="flex items-center justify-between text-xs text-text-tertiary -mt-2">
          <span>
            匹配 <span className="text-text-primary font-medium tabular-nums">{filteredTrades.length}</span> /{" "}
            <span className="tabular-nums">{tradesData?.total_count ?? 0}</span>
          </span>
          {search && (
            <button
              onClick={() => setSearch("")}
              className="text-text-secondary hover:text-accent transition-colors"
            >
              清除筛选
            </button>
          )}
        </div>
      )}

      {/* Equity curve panel */}
      <EquityPanel
        trades={tradesData?.trades ?? []}
        isLoading={tradesLoading}
      />

      {/* Table */}
      {tradesLoading ? (
        <SkeletonTable rows={8} />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[rgba(255,240,220,0.06)]">
                  <Th>ID</Th>
                  <Th>{t("trade.pair")}</Th>
                  <Th>{t("trade.strategy")}</Th>
                  <Th align="right">{t("trade.openRate")}</Th>
                  <Th align="right">{t("trade.closeRate")}</Th>
                  <Th align="right">{t("trade.profit")}</Th>
                  <Th>{t("trade.exitReason")}</Th>
                </tr>
              </thead>
              <tbody>
                {filteredTrades.map((trade, idx) => {
                  const profit = trade.close_profit_abs ?? 0;
                  const positive = profit >= 0;
                  return (
                    <tr
                      key={trade.id}
                      onClick={() => setSelectedTrade(trade)}
                      className={cn(
                        "border-b border-[rgba(255,240,220,0.04)] hover:bg-bg-tertiary/60 cursor-pointer transition-colors",
                        "active:bg-bg-tertiary",
                        idx % 2 === 1 && "bg-bg-tertiary/20",
                      )}
                    >
                      <Td className="text-text-tertiary tabular-nums">#{trade.id}</Td>
                      <Td>
                        <span className="font-semibold text-text-primary">{trade.pair}</span>
                      </Td>
                      <Td>
                        {trade.strategy ? (
                          <Badge tone="muted">{trade.strategy}</Badge>
                        ) : (
                          <span className="text-text-tertiary">—</span>
                        )}
                      </Td>
                      <Td align="right" className="tabular-nums">{trade.open_rate?.toFixed(2) ?? "—"}</Td>
                      <Td align="right" className="tabular-nums">{trade.close_rate?.toFixed(2) ?? "—"}</Td>
                      <Td align="right" className="tabular-nums">
                        <span className={cn("font-semibold", positive ? "text-bull" : "text-bear")}>
                          {positive ? "+" : ""}
                          {profit.toFixed(2)}
                        </span>
                      </Td>
                      <Td>
                        {trade.exit_reason ? (
                          <span className="text-text-secondary text-xs">{trade.exit_reason}</span>
                        ) : (
                          <span className="text-text-tertiary">—</span>
                        )}
                      </Td>
                    </tr>
                  );
                })}
                {filteredTrades.length === 0 && (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState
                        icon={<Search className="w-5 h-5" />}
                        title={search ? `没有匹配 "${search}" 的成交` : t("common.noData")}
                        description={search ? "试试换个关键词，或清除筛选查看全部" : undefined}
                      />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Detail drawer */}
      <Drawer
        open={!!selectedTrade}
        onClose={() => setSelectedTrade(null)}
        title={selectedTrade ? `${selectedTrade.pair} · 交易详情` : ""}
        width="lg"
      >
        {selectedTrade && <TradeDetail trade={selectedTrade} />}
      </Drawer>
    </div>
  );
}

function TradeDetail({ trade }: { trade: Trade }) {
  const profit = trade.close_profit_abs ?? 0;
  const profitPct = trade.close_profit ?? 0;
  const positive = profit >= 0;
  const direction = trade.is_short ? "做空" : "做多";
  const directionTone = trade.is_short ? "bear" : "bull";

  // Compute hold duration
  const holdDuration = (() => {
    if (!trade.open_date || !trade.close_date) return null;
    const ms = new Date(trade.close_date).getTime() - new Date(trade.open_date).getTime();
    const hours = Math.floor(ms / 3_600_000);
    if (hours < 24) return `${hours} 小时`;
    const days = Math.floor(hours / 24);
    return `${days} 天`;
  })();

  return (
    <div className="flex flex-col gap-6">
      {/* Hero: profit + direction */}
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-5">
        <div className="flex items-center justify-between mb-3">
          <Badge tone={directionTone} icon={trade.is_short ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}>
            {direction}
          </Badge>
          {trade.is_open && <Badge tone="info">持仓中</Badge>}
        </div>
        <div className={cn("text-3xl font-semibold tabular-nums tracking-tight", positive ? "text-bull" : "text-bear")}>
          {positive ? "+" : ""}
          {profit.toFixed(2)} <span className="text-base font-medium text-text-tertiary">USDT</span>
        </div>
        <div className={cn("text-sm font-medium tabular-nums mt-1", positive ? "text-bull" : "text-bear")}>
          {positive ? "+" : ""}
          {(profitPct * 100).toFixed(2)}% 收益率
        </div>
      </div>

      {/* Price grid */}
      <div>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary mb-3">价格</h3>
        <div className="grid grid-cols-2 gap-px bg-[rgba(255,240,220,0.06)] rounded-2xl overflow-hidden border border-[rgba(255,240,220,0.06)]">
          <DetailCell icon={<DollarSign className="w-3.5 h-3.5" />} label="开仓价" value={trade.open_rate?.toFixed(2) ?? "—"} />
          <DetailCell icon={<DollarSign className="w-3.5 h-3.5" />} label="平仓价" value={trade.close_rate?.toFixed(2) ?? "—"} />
          <DetailCell icon={<Hash className="w-3.5 h-3.5" />} label="数量" value={trade.amount?.toFixed(5) ?? "—"} />
          <DetailCell icon={<Layers className="w-3.5 h-3.5" />} label="本金" value={`${trade.stake_amount.toFixed(2)} USDT`} />
        </div>
      </div>

      {/* Timeline */}
      <div>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary mb-3">持仓时间线</h3>
        <div className="relative pl-6 space-y-4">
          <TimelineNode
            label="开仓"
            timestamp={trade.open_date}
            tone="bull"
            icon={<Clock className="w-3 h-3" />}
          />
          <TimelineNode
            label="平仓"
            timestamp={trade.close_date}
            tone={trade.is_open ? "info" : "neutral"}
            icon={<Clock className="w-3 h-3" />}
          />
          {holdDuration && (
            <div className="text-xs text-text-tertiary pl-1">
              持仓时长：<span className="text-text-secondary font-medium tabular-nums">{holdDuration}</span>
            </div>
          )}
        </div>
      </div>

      {/* Strategy */}
      <div>
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary mb-3">策略与标签</h3>
        <div className="flex flex-wrap gap-2">
          {trade.strategy ? (
            <Badge tone="default" icon={<Tag className="w-3 h-3" />}>
              {trade.strategy}
            </Badge>
          ) : (
            <span className="text-sm text-text-tertiary">无策略</span>
          )}
          {trade.enter_tag && <Badge tone="muted">{trade.enter_tag}</Badge>}
          {trade.exit_reason && <Badge tone="muted">退出: {trade.exit_reason}</Badge>}
          {trade.leverage > 1 && <Badge tone="warning">{trade.leverage}x 杠杆</Badge>}
        </div>
      </div>
    </div>
  );
}

function DetailCell({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="bg-bg-secondary px-4 py-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-text-tertiary">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <span className="text-sm font-semibold tabular-nums text-text-primary">{value}</span>
    </div>
  );
}

function TimelineNode({
  label,
  timestamp,
  tone,
  icon,
}: {
  label: string;
  timestamp: string | null;
  tone: "bull" | "bear" | "info" | "neutral";
  icon: React.ReactNode;
}) {
  const dotColor =
    tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : tone === "info" ? "bg-info" : "bg-text-tertiary";
  return (
    <div className="relative">
      <div className={cn("absolute -left-[18px] top-0.5 w-2.5 h-2.5 rounded-full", dotColor)} />
      <div className="absolute -left-[22px] top-2.5 bottom-[-16px] w-px bg-[rgba(255,240,220,0.08)] last:hidden" />
      <div className="flex items-center gap-2 mb-0.5">
        <span className="text-xs font-medium text-text-primary">{label}</span>
        <span className="text-text-tertiary">{icon}</span>
      </div>
      <div className="text-xs text-text-tertiary tabular-nums">
        {timestamp ? new Date(timestamp).toLocaleString("zh-CN", { hour12: false }) : "—"}
      </div>
    </div>
  );
}

function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <th
      className={cn(
        "px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  className,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <td className={cn("px-5 py-3", align === "right" ? "text-right" : "text-left", className)}>
      {children}
    </td>
  );
}
