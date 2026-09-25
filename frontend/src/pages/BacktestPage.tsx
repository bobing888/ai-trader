import { useTranslation } from "react-i18next";
import { TrendingUp, TrendingDown, Activity, BarChart3, Calendar } from "lucide-react";

import { Card, CardBody } from "@/components/ui/Card";
import { EquityCurve } from "@/components/ui/EquityCurve";
import { StatCard } from "@/components/ui/StatCard";
import type { LineDataPoint } from "@/lib/equityCurve";
import { cn } from "@/lib/utils";

// Mock backtest data — replace with API when W4 ships
const EQUITY_CURVE: LineDataPoint[] = [
  { value: 10000, label: "01-01" },
  { value: 10240, label: "01-15" },
  { value: 10180, label: "02-01" },
  { value: 10520, label: "02-15" },
  { value: 10890, label: "03-01" },
  { value: 10760, label: "03-15" },
  { value: 11100, label: "04-01" },
  { value: 11450, label: "04-15" },
  { value: 11280, label: "05-01" },
  { value: 11640, label: "05-15" },
  { value: 12100, label: "06-01" },
  { value: 12380, label: "06-15" },
  { value: 12210, label: "07-01" },
  { value: 12680, label: "07-15" },
  { value: 13050, label: "08-01" },
  { value: 13240, label: "08-15" },
  { value: 13480, label: "09-01" },
  { value: 13760, label: "09-15" },
];

const STATS = {
  totalReturn: 37.6,
  sharpe: 1.84,
  maxDrawdown: -8.2,
  winRate: 58.3,
  totalTrades: 142,
  avgHold: "18h",
  profitFactor: 1.92,
  avgWin: 124.5,
  avgLoss: -64.8,
};

const TRADE_DISTRIBUTION = [
  { bucket: "盈利", count: 83, tone: "bull" as const },
  { bucket: "亏损", count: 52, tone: "bear" as const },
  { bucket: "持平", count: 7, tone: "muted" as const },
];

export function BacktestPage() {
  const { t } = useTranslation();
  const totalTrades = TRADE_DISTRIBUTION.reduce((s, b) => s + b.count, 0);

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
            {t("backtest.title")}
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            策略：DoubleEMACrossover · 区间：2026-01-01 ~ 2026-09-15
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge2 tone="accent">Mock 数据</Badge2>
        </div>
      </div>

      {/* Core KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="总收益"
          numericValue={STATS.totalReturn}
          format={(v) => `+${v.toFixed(1)}%`}
          tone="bull"
          change={STATS.totalReturn}
          changeLabel="vs 初始"
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatCard
          label="夏普比"
          numericValue={STATS.sharpe}
          format={(v) => v.toFixed(2)}
          change={STATS.sharpe > 1 ? 12 : -5}
          changeLabel="年化"
          icon={<Activity className="w-4 h-4" />}
        />
        <StatCard
          label="最大回撤"
          numericValue={STATS.maxDrawdown}
          format={(v) => `${v.toFixed(1)}%`}
          tone="bear"
          icon={<TrendingDown className="w-4 h-4" />}
        />
        <StatCard
          label="胜率"
          numericValue={STATS.winRate}
          format={(v) => `${v.toFixed(1)}%`}
          icon={<BarChart3 className="w-4 h-4" />}
        />
      </div>

      {/* Equity curve */}
      <Card>
        <div className="px-5 py-4 border-b border-[rgba(255,240,220,0.06)] flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">收益曲线</h3>
            <p className="text-[11px] text-text-tertiary mt-0.5">从 10,000 USDT 起，累计净值</p>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-text-tertiary">当前净值</div>
            <div className="text-base font-semibold tabular-nums text-bull">
              {EQUITY_CURVE[EQUITY_CURVE.length - 1].value.toLocaleString()}
            </div>
          </div>
        </div>
        <div className="p-2">
          <EquityCurve data={EQUITY_CURVE} height={220} />
        </div>
      </Card>

      {/* Secondary stats + distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Card>
          <CardBody className="space-y-3">
            <h3 className="text-sm font-semibold text-text-primary">交易统计</h3>
            <StatRow label="总交易数" value={String(STATS.totalTrades)} icon={<BarChart3 className="w-3.5 h-3.5" />} />
            <StatRow label="盈亏比" value={STATS.profitFactor.toFixed(2)} icon={<Activity className="w-3.5 h-3.5" />} />
            <StatRow label="平均持仓" value={STATS.avgHold} icon={<Calendar className="w-3.5 h-3.5" />} />
          </CardBody>
        </Card>
        <Card>
          <CardBody className="space-y-3">
            <h3 className="text-sm font-semibold text-text-primary">盈亏分布</h3>
            <StatRow label="平均盈利" value={`+${STATS.avgWin.toFixed(2)}`} valueClass="text-bull" />
            <StatRow label="平均亏损" value={STATS.avgLoss.toFixed(2)} valueClass="text-bear" />
            <StatRow label="盈亏差" value={`${(STATS.avgWin + STATS.avgLoss).toFixed(2)}`} />
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <h3 className="text-sm font-semibold text-text-primary mb-3">结果分布</h3>
            <div className="space-y-2.5">
              {TRADE_DISTRIBUTION.map((b) => {
                const pct = (b.count / totalTrades) * 100;
                return (
                  <div key={b.bucket}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-text-secondary">{b.bucket}</span>
                      <span className="text-text-primary font-medium tabular-nums">
                        {b.count} <span className="text-text-tertiary">({pct.toFixed(0)}%)</span>
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-700",
                          b.tone === "bull" && "bg-bull",
                          b.tone === "bear" && "bg-bear",
                          b.tone === "muted" && "bg-text-tertiary",
                        )}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function StatRow({
  label,
  value,
  icon,
  valueClass,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-text-tertiary">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <span className={cn("text-sm font-semibold tabular-nums", valueClass ?? "text-text-primary")}>{value}</span>
    </div>
  );
}

function Badge2({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "accent" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center h-6 px-2.5 rounded-full text-[11px] font-medium tracking-wide",
        tone === "accent"
          ? "bg-accent/10 text-accent border border-accent/20"
          : "bg-bg-tertiary text-text-secondary border border-[rgba(255,240,220,0.06)]",
      )}
    >
      {children}
    </span>
  );
}
