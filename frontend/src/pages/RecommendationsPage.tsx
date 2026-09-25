import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowUpDown,
  RefreshCw,
  Shield,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import { fetchBatchSignals, type BatchSignalItem, type BatchSignalsResponse } from "@/lib/api";
import { useKlineStore } from "@/stores/klineStore";

const DEFAULT_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"];
const TIMEFRAMES = ["1h", "4h", "1d"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

type SortKey = "confidence" | "regime" | "pair";

export function RecommendationsPage() {
  const { t } = useTranslation();
  const { symbol: _storeSymbol } = useKlineStore();
  const [selectedPairs] = useState<string[]>(DEFAULT_PAIRS);
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const [directionFilter, setDirectionFilter] = useState<"all" | "long" | "short">("all");

  const { data, isLoading, isFetching, refetch, error } = useQuery<BatchSignalsResponse, Error>({
    queryKey: ["batch-signals", selectedPairs, timeframe],
    queryFn: () => fetchBatchSignals(selectedPairs, timeframe),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const sortedSignals = (data?.ranked ?? []).filter(
    (item: BatchSignalItem) => item.has_signal && item.signal,
  ).sort((a: BatchSignalItem, b: BatchSignalItem) => {
    if (sortKey === "confidence") {
      return (b.signal?.confidence ?? 0) - (a.signal?.confidence ?? 0);
    }
    if (sortKey === "pair") {
      return a.pair.localeCompare(b.pair);
    }
    // regime sort
    const regimeOrder: Record<string, number> = { crisis: 0, bear: 1, choppy: 2, bull: 3 };
    return (regimeOrder[a.regime?.regime ?? "choppy"] ?? 2) - (regimeOrder[b.regime?.regime ?? "choppy"] ?? 2);
  }).filter((item: BatchSignalItem) => {
    if (directionFilter === "all") return true;
    return item.signal?.direction === directionFilter;
  });

  const globalRegime = data?.regime_global;

  return (
    <div className="flex flex-col gap-5">
      {/* Page header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("nav.recommendations")}</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            {isLoading ? "分析中..." : `${selectedPairs.length} 个交易对 · ${timeframe} 周期`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Timeframe selector */}
          <div className="flex rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.08)] p-0.5">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={cn(
                  "px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                  timeframe === tf
                    ? "bg-bg-tertiary text-text-primary"
                    : "text-text-secondary hover:text-text-primary",
                )}
              >
                {tf}
              </button>
            ))}
          </div>
          {/* Refresh */}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.08)] text-text-secondary hover:text-text-primary transition-colors"
            aria-label="刷新信号"
          >
            <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* Global regime banner */}
      {globalRegime && (
        <RegimeBanner regime={globalRegime} />
      )}

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Direction filter */}
        <div className="flex rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.08)] p-0.5">
          {(["all", "long", "short"] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDirectionFilter(d)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                directionFilter === d
                  ? d === "long"
                    ? "bg-bull/15 text-bull border border-bull/25"
                    : d === "short"
                      ? "bg-bear/15 text-bear border border-bear/25"
                      : "bg-bg-tertiary text-text-primary"
                  : "text-text-secondary hover:text-text-primary",
              )}
            >
              {d === "long" && <TrendingUp className="w-3 h-3" />}
              {d === "short" && <TrendingDown className="w-3 h-3" />}
              {d === "all" ? "全部" : d === "long" ? "做多" : "做空"}
            </button>
          ))}
        </div>

        {/* Sort */}
        <div className="flex items-center gap-2 ml-auto">
          <ArrowUpDown className="w-3.5 h-3.5 text-text-tertiary" />
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="bg-bg-secondary border border-[rgba(255,240,220,0.08)] text-xs text-text-secondary rounded-full px-3 py-1.5 outline-none focus:border-accent/50"
          >
            <option value="confidence">按置信度</option>
            <option value="pair">按币种</option>
            <option value="regime">按市场状态</option>
          </select>
        </div>
      </div>

      {/* Error */}
      {error && (
        <Card>
          <CardBody className="flex flex-col items-center gap-3 py-10 text-center">
            <AlertTriangle className="w-8 h-8 text-warning" />
            <p className="text-sm text-text-secondary">信号引擎连接失败，请检查后端服务</p>
            <button
              onClick={() => refetch()}
              className="px-4 py-2 bg-accent/10 text-accent border border-accent/25 rounded-full text-xs font-medium hover:bg-accent/20 transition-colors"
            >
              重试
            </button>
          </CardBody>
        </Card>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Empty */}
      {!isLoading && !error && sortedSignals.length === 0 && (
        <EmptyState
          icon={<Target className="w-6 h-6" />}
          title="当前无推荐信号"
          description="市场状态不适合入场，建议观望等待机会"
          action={
            <button
              onClick={() => setDirectionFilter("all")}
              className="mt-3 px-4 py-2 bg-accent/10 text-accent border border-accent/25 rounded-full text-xs font-medium hover:bg-accent/20 transition-colors"
            >
              查看全部信号
            </button>
          }
        />
      )}

      {/* Signals grid */}
      {!isLoading && !error && sortedSignals.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sortedSignals.map((item: BatchSignalItem) => (
            <SignalCard key={item.pair} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Regime Banner ───────────────────────────────────────────────────────────────

function RegimeBanner({ regime }: { regime: BatchSignalsResponse["regime_global"] }) {
  if (!regime) return null;
  const regimeConfig: Record<string, { color: string; bg: string; border: string; icon: typeof TrendingUp; label: string }> = {
    bull: { color: "text-bull", bg: "bg-bull/10", border: "border-bull/25", icon: TrendingUp, label: "上涨趋势" },
    bear: { color: "text-bear", bg: "bg-bear/10", border: "border-bear/25", icon: TrendingDown, label: "下跌趋势" },
    choppy: { color: "text-warning", bg: "bg-warning/10", border: "border-warning/25", icon: ArrowUpDown, label: "震荡区间" },
    crisis: { color: "text-bear", bg: "bg-bear/10", border: "border-bear/25", icon: AlertTriangle, label: "极端波动" },
  };
  const cfg = regimeConfig[regime.regime] ?? regimeConfig.choppy;
  const Icon = cfg.icon;
  return (
    <div className={cn("flex items-center gap-3 rounded-2xl px-4 py-3 border", cfg.bg, cfg.border)}>
      <Icon className={cn("w-5 h-5 shrink-0", cfg.color)} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn("text-sm font-semibold", cfg.color)}>{cfg.label}</span>
          <Badge tone="default" className="text-[10px]">
            {regime.description?.split("·")[1] ?? regime.description}
          </Badge>
        </div>
        <p className="text-xs text-text-tertiary mt-0.5">
          置信度 {(regime.confidence * 100).toFixed(0)}% · 各状态概率：
          {Object.entries(regime.regime_probs)
            .sort(([, a], [, b]) => b - a)
            .map(([k, v]) => `${k === regime.regime ? "★" : ""}${(v * 100).toFixed(0)}%${k}`)
            .join(" · ")}
        </p>
      </div>
    </div>
  );
}

// ─── Signal Card ────────────────────────────────────────────────────────────────

function SignalCard({ item }: { item: BatchSignalItem }) {
  const signal = item.signal!;
  const isLong = signal.direction === "long";
  const confidence = signal.confidence;
  const strength: "strong" | "moderate" | "weak" =
    confidence >= 0.75 ? "strong" : confidence >= 0.55 ? "moderate" : "weak";
  const confColor = isLong ? "text-bull" : "text-bear";
  const confBg = isLong ? "bg-bull/10 border-bull/25" : "bg-bear/10 border-bear/25";
  const strengthLabel = { strong: "强", moderate: "中", weak: "弱" }[strength];

  return (
    <Card className={cn("transition-all hover:border-[rgba(255,240,220,0.15)]", confBg)}>
      <CardBody className="space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className={cn("w-8 h-8 rounded-xl flex items-center justify-center", isLong ? "bg-bull/15" : "bg-bear/15")}>
              {isLong
                ? <TrendingUp className="w-4 h-4 text-bull" />
                : <TrendingDown className="w-4 h-4 text-bear" />}
            </div>
            <div>
              <div className="text-sm font-semibold text-text-primary">{item.pair}</div>
              <Badge tone={isLong ? "bull" : "bear"} className="text-[10px] mt-0.5">
                {isLong ? "做多" : "做空"}
              </Badge>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className={cn("text-xl font-bold tabular-nums tracking-tight", confColor)}>
              {(confidence * 100).toFixed(0)}%
            </div>
            <Badge
              tone={strength === "strong" ? "bull" : strength === "moderate" ? "warning" : "default"}
              className="text-[10px]"
            >
              {strengthLabel}信号
            </Badge>
          </div>
        </div>

        {/* Reasons */}
        <div className="space-y-1">
          {signal.reasons.slice(0, 3).map((r, i) => (
            <div key={i} className="flex items-start gap-1.5">
              <span className="mt-0.5 w-1 h-1 rounded-full bg-accent shrink-0" />
              <span className="text-xs text-text-secondary">{r}</span>
            </div>
          ))}
          {signal.reasons.length > 3 && (
            <span className="text-[10px] text-text-tertiary">+{signal.reasons.length - 3} 条</span>
          )}
        </div>

        {/* Strategies */}
        <div className="flex flex-wrap gap-1">
          {signal.contributing_strategies.map((s) => (
            <Badge key={s} tone="default" className="text-[10px]">
              {s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </Badge>
          ))}
        </div>

        {/* Entry zones */}
        {signal.entry_zones.length > 0 && (
          <div className="rounded-xl bg-bg-tertiary/60 border border-[rgba(255,240,220,0.06)] px-3 py-2 space-y-0.5">
            <div className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary">入场参考</div>
            {signal.entry_zones.map((z, i) => (
              <div key={i} className="text-xs text-text-secondary">{z}</div>
            ))}
          </div>
        )}

        {/* Risk warnings */}
        {signal.risk_warnings.length > 0 && (
          <div className="flex items-center gap-1.5 text-[11px] text-warning">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            {signal.risk_warnings[0]}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-1 border-t border-[rgba(255,240,220,0.06)]">
          <div className="flex items-center gap-1 text-[10px] text-text-tertiary">
            <Shield className="w-3 h-3" />
            策略置信度 {signal.regime_confidence > 0 ? `${(signal.regime_confidence * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="text-[10px] text-text-tertiary tabular-nums">
            {new Date(signal.generated_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
