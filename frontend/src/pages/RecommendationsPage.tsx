import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowUpDown,
  BarChart2,
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

// ─── Page-level summary ────────────────────────────────────────────────────────

function PageSummaryBar({ items }: { items: BatchSignalItem[] }) {
  if (items.length === 0) return null;

  const longCount = items.filter((i) => i.signal?.direction === "long").length;
  const shortCount = items.filter((i) => i.signal?.direction === "short").length;
  const neutralCount = items.length - longCount - shortCount;

  const confidences = items
    .map((i) => i.signal?.confidence ?? 0)
    .filter((c) => c > 0);
  const avgConf =
    confidences.length > 0
      ? confidences.reduce((a, b) => a + b, 0) / confidences.length
      : 0;

  let overall = "中性";
  if (longCount > shortCount * 1.5) overall = "偏多";
  else if (shortCount > longCount * 1.5) overall = "偏空";
  else if (longCount > shortCount) overall = "略偏多";
  else if (shortCount > longCount) overall = "略偏空";

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.08)] px-4 py-3">
      {/* Direction counts */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <TrendingUp className="w-4 h-4 text-bull" />
          <span className="text-sm font-semibold text-bull">{longCount}</span>
          <span className="text-xs text-text-secondary">做多</span>
        </div>
        <div className="w-px h-4 bg-[rgba(255,240,220,0.08)]" />
        <div className="flex items-center gap-1.5">
          <TrendingDown className="w-4 h-4 text-bear" />
          <span className="text-sm font-semibold text-bear">{shortCount}</span>
          <span className="text-xs text-text-secondary">做空</span>
        </div>
        {neutralCount > 0 && (
          <>
            <div className="w-px h-4 bg-[rgba(255,240,220,0.08)]" />
            <div className="flex items-center gap-1.5">
              <ArrowUpDown className="w-4 h-4 text-warning" />
              <span className="text-sm font-semibold text-warning">{neutralCount}</span>
              <span className="text-xs text-text-secondary">观望</span>
            </div>
          </>
        )}
      </div>

      <div className="w-px h-4 bg-[rgba(255,240,220,0.08)]" />

      {/* Avg confidence */}
      <div className="flex items-center gap-1.5">
        <BarChart2 className="w-3.5 h-3.5 text-text-tertiary" />
        <span className="text-xs text-text-secondary">平均置信度</span>
        <span
          className={cn(
            "text-sm font-bold tabular-nums",
            avgConf >= 0.6
              ? "text-bull"
              : avgConf <= 0.4
                ? "text-bear"
                : "text-warning",
          )}
        >
          {(avgConf * 100).toFixed(0)}%
        </span>
      </div>

      <div className="w-px h-4 bg-[rgba(255,240,220,0.08)]" />

      {/* Overall AI judgment */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-text-secondary">AI 整体判断：</span>
        <Badge
          tone={
            overall === "偏多" || overall === "略偏多"
              ? "bull"
              : overall === "偏空" || overall === "略偏空"
                ? "bear"
                : "warning"
          }
          className="text-xs font-semibold"
        >
          {overall}
        </Badge>
      </div>
    </div>
  );
}

// ─── Direction Badge ───────────────────────────────────────────────────────────

function DirectionBadge({ direction }: { direction: "long" | "short" }) {
  const isLong = direction === "long";
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xl font-bold tracking-tight min-w-[80px] justify-center",
        isLong
          ? "bg-bull/15 text-bull border-2 border-bull/30"
          : "bg-bear/15 text-bear border-2 border-bear/30",
      )}
    >
      {isLong ? (
        <TrendingUp className="w-6 h-6" />
      ) : (
        <TrendingDown className="w-6 h-6" />
      )}
      {isLong ? "做多" : "做空"}
    </div>
  );
}

// ─── Confidence Ring ──────────────────────────────────────────────────────────

function ConfidenceRing({ confidence, direction }: { confidence: number; direction: "long" | "short" }) {
  const pct = Math.round(confidence * 100);
  const isLong = direction === "long";
  const color = isLong ? "#22c55e" : "#ef4444";
  const r = 22;
  const circumference = 2 * Math.PI * r;
  const strokeDashoffset = circumference * (1 - confidence);

  let levelLabel: string;
  let levelColor: string;
  if (pct >= 70) {
    levelLabel = "强";
    levelColor = isLong ? "text-bull" : "text-bear";
  } else if (pct >= 50) {
    levelLabel = "中";
    levelColor = "text-warning";
  } else {
    levelLabel = "弱";
    levelColor = "text-text-secondary";
  }

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-14 h-14">
        {/* Background circle */}
        <svg className="w-full h-full -rotate-90" viewBox="0 0 56 56">
          <circle
            cx="28"
            cy="28"
            r={r}
            fill="none"
            stroke="rgba(255,240,220,0.08)"
            strokeWidth="5"
          />
          <circle
            cx="28"
            cy="28"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn("text-sm font-bold tabular-nums", levelColor)}>{pct}%</span>
        </div>
      </div>
      <span className={cn("text-[10px] font-medium", levelColor)}>{levelLabel}信号</span>
    </div>
  );
}

// ─── Regime Tag ───────────────────────────────────────────────────────────────

const REGIME_CONFIG: Record<
  string,
  { label: string; tone: "bull" | "bear" | "warning" | "info" }
> = {
  bull: { label: "多头", tone: "bull" },
  bear: { label: "空头", tone: "bear" },
  choppy: { label: "震荡", tone: "warning" },
  crisis: { label: "危机", tone: "bear" },
};

function RegimeTag({ regime }: { regime: string | undefined }) {
  const cfg = REGIME_CONFIG[regime ?? ""] ?? REGIME_CONFIG.choppy;
  return <Badge tone={cfg.tone}>{cfg.label}</Badge>;
}

// ─── Timeframe Tag ────────────────────────────────────────────────────────────

function TimeframeTag({ timeframe }: { timeframe: string | undefined }) {
  return (
    <Badge tone="info" className="text-[11px]">
      {timeframe ?? "—"}
    </Badge>
  );
}

// ─── Signal Reasons ───────────────────────────────────────────────────────────

function SignalReasons({ reasons }: { reasons: string[] }) {
  const display = reasons.slice(0, 5);
  return (
    <div className="space-y-1">
      {display.map((r, i) => (
        <div key={i} className="flex items-start gap-1.5">
          <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
          <span className="text-xs text-text-secondary leading-relaxed">{r}</span>
        </div>
      ))}
      {reasons.length > 5 && (
        <span className="text-[10px] text-text-tertiary pl-3.5">+{reasons.length - 5} 条</span>
      )}
    </div>
  );
}

// ─── Risk Bar ─────────────────────────────────────────────────────────────────

function RiskBar({ item }: { item: BatchSignalItem }) {
  const signal = item.signal!;
  return (
    <div className="rounded-xl bg-bg-tertiary/50 border border-[rgba(255,240,220,0.06)] px-3 py-2 space-y-1">
      <div className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary mb-1.5">
        风险指标
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {signal.entry_zones[0] && (
          <div className="flex justify-between items-center">
            <span className="text-[10px] text-text-tertiary">入场</span>
            <span className="text-xs font-medium text-text-primary tabular-nums">
              {signal.entry_zones[0].replace(/\s+/g, " ").trim() || "—"}
            </span>
          </div>
        )}
        {signal.risk_warnings[0] && (
          <div className="flex justify-between items-center">
            <span className="text-[10px] text-text-tertiary">风险</span>
            <span className="text-[10px] text-warning">{signal.risk_warnings[0]}</span>
          </div>
        )}
        <div className="flex justify-between items-center">
          <span className="text-[10px] text-text-tertiary">置信度</span>
          <span
            className={cn(
              "text-xs font-semibold tabular-nums",
              signal.confidence >= 0.6
                ? "text-bull"
                : signal.confidence <= 0.4
                  ? "text-bear"
                  : "text-warning",
            )}
          >
            {(signal.confidence * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-[10px] text-text-tertiary">市态</span>
          <RegimeTag regime={signal.regime} />
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

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

      {/* Page Summary Bar */}
      {!isLoading && sortedSignals.length > 0 && (
        <PageSummaryBar items={sortedSignals} />
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
            <EnhancedSignalCard key={item.pair} item={item} timeframe={timeframe} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Regime Banner ─────────────────────────────────────────────────────────────

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

// ─── Enhanced Signal Card ──────────────────────────────────────────────────────

function EnhancedSignalCard({ item, timeframe }: { item: BatchSignalItem; timeframe: string }) {
  const signal = item.signal!;
  const isLong = signal.direction === "long";

  return (
    <Card className={cn(
      "transition-all hover:border-[rgba(255,240,220,0.15)]",
      isLong ? "border-l-2 border-l-bull/40" : "border-l-2 border-l-bear/40",
    )}>
      <CardBody className="space-y-3">
        {/* ── Section A: Direction + Confidence (visual intensity zone) ── */}
        <div className="flex items-center justify-between gap-3">
          {/* Large direction badge */}
          <DirectionBadge direction={signal.direction} />

          {/* Pair + tags */}
          <div className="flex flex-col items-end gap-1.5">
            <div className="text-sm font-bold text-text-primary">{item.pair}</div>
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              <RegimeTag regime={signal.regime} />
              <TimeframeTag timeframe={timeframe} />
            </div>
          </div>
        </div>

        {/* Confidence ring */}
        <div className="flex justify-center">
          <ConfidenceRing confidence={signal.confidence} direction={signal.direction} />
        </div>

        {/* ── Section B: Signal reasons summary ── */}
        {signal.reasons.length > 0 && (
          <div>
            <div className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary mb-1.5">
              信号摘要
            </div>
            <SignalReasons reasons={signal.reasons} />
          </div>
        )}

        {/* Contributing strategies */}
        {signal.contributing_strategies.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {signal.contributing_strategies.map((s) => (
              <Badge key={s} tone="default" className="text-[10px]">
                {s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
              </Badge>
            ))}
          </div>
        )}

        {/* ── Section C: Risk bar ── */}
        <RiskBar item={item} />

        {/* ── Footer ── */}
        <div className="flex items-center justify-between pt-1 border-t border-[rgba(255,240,220,0.06)]">
          <div className="flex items-center gap-1 text-[10px] text-text-tertiary">
            <Shield className="w-3 h-3" />
            市态置信 {signal.regime_confidence > 0 ? `${(signal.regime_confidence * 100).toFixed(0)}%` : "—"}
          </div>
          <div className="text-[10px] text-text-tertiary tabular-nums">
            {new Date(signal.generated_at).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
