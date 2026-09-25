import { useMemo } from "react";
import { TrendingUp, TrendingDown, BarChart3, AlertTriangle, Trophy, Skull } from "lucide-react";

import { Card, CardBody } from "@/components/ui/Card";
import { EquityCurve } from "@/components/EquityCurve";
import { computeEquityStats, buildEquityCurve, type EquityStats } from "@/lib/equity";
import type { Trade } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface EquityPanelProps {
  trades: Trade[];
  isLoading?: boolean;
}

export function EquityPanel({ trades, isLoading }: EquityPanelProps) {
  const { curve, stats } = useMemo(() => {
    return {
      curve: buildEquityCurve(trades),
      stats: computeEquityStats(trades),
    };
  }, [trades]);

  return (
    <Card className="overflow-hidden">
      <CardBody className="space-y-4">
        <div className="flex items-end justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">累计盈亏曲线</h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              基于 {stats.closedCount} 笔已平仓交易 · 含未实现盈亏估算
            </p>
          </div>
          <TotalBadge stats={stats} />
        </div>

        <EquityCurve points={curve} />

        {/* KPI strip */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 pt-3 border-t border-[rgba(255,240,220,0.06)]">
          <KpiCell
            label="最大回撤"
            value={stats.maxDrawdownPct > 0 ? `${stats.maxDrawdownPct.toFixed(2)}%` : "—"}
            tone={stats.maxDrawdownPct > 30 ? "bear" : stats.maxDrawdownPct > 15 ? "warning" : "neutral"}
            icon={<AlertTriangle className="w-3 h-3" />}
            loading={isLoading}
          />
          <KpiCell
            label="盈亏比"
            value={Number.isFinite(stats.profitFactor) ? stats.profitFactor.toFixed(2) : "∞"}
            tone={stats.profitFactor >= 1.5 ? "bull" : stats.profitFactor >= 1 ? "neutral" : "bear"}
            icon={<BarChart3 className="w-3 h-3" />}
            loading={isLoading}
          />
          <KpiCell
            label="平均盈利"
            value={stats.avgWin > 0 ? `+${stats.avgWin.toFixed(2)}` : "—"}
            tone="bull"
            icon={<TrendingUp className="w-3 h-3" />}
            loading={isLoading}
          />
          <KpiCell
            label="平均亏损"
            value={stats.avgLoss < 0 ? stats.avgLoss.toFixed(2) : "—"}
            tone="bear"
            icon={<TrendingDown className="w-3 h-3" />}
            loading={isLoading}
          />
          <KpiCell
            label="最佳单笔"
            value={stats.bestTrade > 0 ? `+${stats.bestTrade.toFixed(2)}` : "—"}
            tone="bull"
            icon={<Trophy className="w-3 h-3" />}
            loading={isLoading}
          />
          <KpiCell
            label="最差单笔"
            value={stats.worstTrade < 0 ? stats.worstTrade.toFixed(2) : "—"}
            tone="bear"
            icon={<Skull className="w-3 h-3" />}
            loading={isLoading}
          />
        </div>
      </CardBody>
    </Card>
  );
}

function TotalBadge({ stats }: { stats: EquityStats }) {
  const positive = stats.total >= 0;
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full",
        positive ? "bg-bull/10 border border-bull/25" : "bg-bear/10 border border-bear/25",
      )}
    >
      <span className={cn("text-xs font-medium", positive ? "text-bull" : "text-bear")}>
        {positive ? "累计净利" : "累计净亏"}
      </span>
      <span
        className={cn(
          "text-base font-semibold tabular-nums tracking-tight",
          positive ? "text-bull" : "text-bear",
        )}
      >
        {positive ? "+" : ""}
        {stats.total.toFixed(2)}
      </span>
    </div>
  );
}

interface KpiCellProps {
  label: string;
  value: string;
  tone: "bull" | "bear" | "warning" | "neutral";
  icon: React.ReactNode;
  loading?: boolean;
}

function KpiCell({ label, value, tone, icon, loading }: KpiCellProps) {
  const colorClass =
    tone === "bull"
      ? "text-bull"
      : tone === "bear"
        ? "text-bear"
        : tone === "warning"
          ? "text-warning"
          : "text-text-primary";
  return (
    <div className="rounded-xl bg-bg-tertiary/60 border border-[rgba(255,240,220,0.06)] px-3 py-2.5 flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-text-tertiary">
        <span className={cn(tone === "bull" || tone === "bear" ? colorClass : "text-text-tertiary")}>
          {icon}
        </span>
        {label}
      </div>
      <div className={cn("text-sm font-semibold tabular-nums", colorClass)}>
        {loading ? "—" : value}
      </div>
    </div>
  );
}
