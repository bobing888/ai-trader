import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FollowDialog } from "@/components/FollowDialog";
import {
  AlertTriangle,
  ArrowUpDown,
  BarChart2,
  RefreshCw,
  Shield,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import {
  fetchBatchSignals,
  type BatchSignalItem,
  type BatchSignalsResponse,
  type TimeframeCategory,
} from "@/lib/api";
import { useKlineStore } from "@/stores/klineStore";

const DEFAULT_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"];

// v2: 4 档分类（超短线/短线/中线/长线）
type RawTimeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";
interface TimeframeOption {
  value: RawTimeframe;
  category: TimeframeCategory;
  label: string;
  shortLabel: string;
  defaultLeverage: number;
  icon: typeof Zap;
}

const TIMEFRAMES: TimeframeOption[] = [
  { value: "5m",  category: "ultra_short", label: "超短线",   shortLabel: "5m",  defaultLeverage: 5, icon: Zap },
  { value: "15m", category: "short",       label: "短线",     shortLabel: "15m", defaultLeverage: 3, icon: TrendingUp },
  { value: "1h",  category: "mid",         label: "中线",     shortLabel: "1h",  defaultLeverage: 2, icon: BarChart2 },
  { value: "1d",  category: "long",        label: "长线",     shortLabel: "1d",  defaultLeverage: 1, icon: Shield },
];

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

// ─── Direction Badge (inlined into EnhancedSignalCard) ────────────────────────

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

// ─── v2: Fast-path Indicator ──────────────────────────────────────────────────

function FastPathBadge() {
  return (
    <Badge tone="info" className="text-[10px]">
      <Sparkles className="w-2.5 h-2.5 mr-0.5" />
      强信号
    </Badge>
  );
}

// ─── Timeframe Tag ────────────────────────────────────────────────────────────

function TimeframeTag({ timeframe }: { timeframe: string | undefined }) {
  return (
    <Badge tone="info" className="text-[11px]">
      {timeframe ?? "—"}
    </Badge>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function RecommendationsPage() {
  const { t } = useTranslation();
  const { symbol: _storeSymbol } = useKlineStore();
  const [selectedPairs] = useState<string[]>(DEFAULT_PAIRS);
  const [timeframeOpt, setTimeframeOpt] = useState<TimeframeOption>(TIMEFRAMES[2]); // 默认 1h 中线
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const [directionFilter, setDirectionFilter] = useState<"all" | "long" | "short">("all");

  const { data, isLoading, isFetching, refetch, error } = useQuery<BatchSignalsResponse, Error>({
    queryKey: ["batch-signals", selectedPairs, timeframeOpt.value],
    queryFn: () => fetchBatchSignals(selectedPairs, timeframeOpt.value),
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
  const TFIcon = timeframeOpt.icon;

  return (
    <div className="flex flex-col gap-5">
      {/* Page header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t("nav.recommendations")}</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            {isLoading
              ? "分析中..."
              : `${selectedPairs.length} 个交易对 · ${timeframeOpt.label}（${timeframeOpt.value}）`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* v2: 4 档 Timeframe selector（超短线/短线/中线/长线） */}
          <div className="flex rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.08)] p-0.5">
            {TIMEFRAMES.map((tf) => {
              const Icon = tf.icon;
              const isActive = timeframeOpt.value === tf.value;
              return (
                <button
                  key={tf.value}
                  onClick={() => setTimeframeOpt(tf)}
                  className={cn(
                    "flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                    isActive
                      ? "bg-bg-tertiary text-text-primary"
                      : "text-text-secondary hover:text-text-primary",
                  )}
                  title={`${tf.label} · 默认杠杆 ${tf.defaultLeverage}x`}
                >
                  <Icon className="w-3 h-3" />
                  {tf.shortLabel}
                </button>
              );
            })}
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

      {/* v2: Timeframe category hint */}
      <div className="flex items-center gap-2 text-xs text-text-tertiary -mt-2">
        <TFIcon className="w-3 h-3" />
        <span>
          {timeframeOpt.label}模式 ·
          默认杠杆 {timeframeOpt.defaultLeverage}x ·
          {timeframeOpt.category === "ultra_short" && " 快进快出严控止损"}
          {timeframeOpt.category === "short" && " 短线操作，1-3 天持仓"}
          {timeframeOpt.category === "mid" && " 波段操作，数天持仓"}
          {timeframeOpt.category === "long" && " 趋势跟踪，数周持仓"}
        </span>
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
          description={`${timeframeOpt.label}周期下市场状态不适合入场，可尝试切换其他周期或刷新`}
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
            <EnhancedSignalCard key={item.pair} item={item} timeframe={timeframeOpt.value} />
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
  const entryT1 = signal.entry_levels?.[0]?.price;
  const sl = signal.stop_loss_price ?? null;
  const tp1 = signal.take_profit_1_price ?? null;
  const tp2 = signal.take_profit_2_price ?? null;
  const confPct = Math.round(signal.confidence * 100);
  const leverage = signal.suggested_leverage ?? 1;

  // 跟单 dialog state（卡片内直接管理）
  const [followOpen, setFollowOpen] = useState(false);
  // OKX 形态 (BTC-USDT) → binance 形态 (BTCUSDT) 转换
  const okxPair = item.pair.endsWith("USDT")
    ? item.pair.replace(/USDT$/, "-USDT")
    : item.pair;

  // 置信度进度条颜色
  const confBarColor = isLong ? "bg-bull" : "bg-bear";
  const confBarTrack = isLong ? "bg-bull/15" : "bg-bear/15";

  return (
    <Card
      data-testid={`signal-card-${item.pair}`}
      className={cn(
        "transition-all hover:border-[rgba(255,240,220,0.2)] hover:-translate-y-0.5",
        "border-t-[3px]",
        isLong ? "border-t-bull" : "border-t-bear",
      )}
    >
      <CardBody className="p-5 space-y-4">
        {/* ── Row 1: Pair + Direction badge ─────────────────────────────── */}
        <div className="flex items-start justify-between gap-3">
          {/* Pair + timeframe + regime */}
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-text-primary tracking-tight leading-none">
                {item.pair.replace("USDT", "/USDT")}
              </span>
              <TimeframeTag timeframe={timeframe} />
            </div>
            <div className="flex items-center gap-1.5 flex-wrap">
              <RegimeTag regime={signal.regime} />
              {signal.fast_path && <FastPathBadge />}
              {signal.timeframe_category &&
                signal.timeframe_category !== "long" && (
                  <span className="inline-flex items-center gap-0.5 h-6 px-2.5 rounded-full text-[11px] font-bold tabular-nums bg-warning/10 text-warning border border-warning/20">
                    <Zap className="w-3 h-3" />
                    {leverage}x
                  </span>
                )}
              {signal.quality && signal.quality !== "reject" && (
                <Badge
                  tone={
                    signal.quality === "high"
                      ? "bull"
                      : signal.quality === "medium"
                        ? "warning"
                        : "bear"
                  }
                  className="text-[11px]"
                >
                  {signal.quality === "high"
                    ? "高质"
                    : signal.quality === "medium"
                      ? "中质"
                      : "低质"}
                </Badge>
              )}
            </div>
          </div>

          {/* Direction pill — 视觉焦点 */}
          <div
            className={cn(
              "shrink-0 flex items-center gap-2 py-2.5 px-4 rounded-xl text-2xl font-extrabold tracking-tight",
              isLong
                ? "bg-bull/15 text-bull ring-1 ring-bull/30"
                : "bg-bear/15 text-bear ring-1 ring-bear/30",
            )}
          >
            {isLong ? (
              <TrendingUp className="w-7 h-7" />
            ) : (
              <TrendingDown className="w-7 h-7" />
            )}
            {isLong ? "做多" : "做空"}
          </div>
        </div>

        {/* ── Row 2: Confidence bar (单行大字号) ──────────────────────── */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-text-tertiary shrink-0">置信度</span>
          <div className={cn("flex-1 h-2 rounded-full overflow-hidden", confBarTrack)}>
            <div
              className={cn("h-full rounded-full transition-all duration-700", confBarColor)}
              style={{ width: `${confPct}%` }}
            />
          </div>
          <span
            className={cn(
              "text-xl font-bold tabular-nums shrink-0 min-w-[3.5rem] text-right",
              confPct >= 60 ? (isLong ? "text-bull" : "text-bear") : "text-warning",
            )}
          >
            {confPct}%
          </span>
        </div>

        {/* ── Row 3: 价格区 (Entry / SL / TP) — 3 列等宽大字号 ────────── */}
        <div className="grid grid-cols-3 gap-2">
          {/* Entry */}
          <div className="rounded-lg bg-bg-tertiary/60 border border-[rgba(255,240,220,0.06)] px-3 py-2.5">
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-text-tertiary mb-1">
              <Wallet className="w-3 h-3" />
              入场
            </div>
            <div className="text-xl font-bold text-text-primary tabular-nums leading-tight font-mono">
              {entryT1 ? entryT1.toFixed(2) : "—"}
            </div>
          </div>
          {/* SL */}
          <div className="rounded-lg bg-bg-tertiary/60 border border-bear/20 px-3 py-2.5">
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-bear/80 mb-1">
              <Shield className="w-3 h-3" />
              止损
            </div>
            <div className="text-xl font-bold text-bear tabular-nums leading-tight font-mono">
              {sl != null ? sl.toFixed(2) : "—"}
            </div>
          </div>
          {/* TP1 */}
          <div className="rounded-lg bg-bg-tertiary/60 border border-bull/20 px-3 py-2.5">
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-bull/80 mb-1">
              <Target className="w-3 h-3" />
              止盈
            </div>
            <div className="text-xl font-bold text-bull tabular-nums leading-tight font-mono">
              {tp1 != null ? tp1.toFixed(2) : "—"}
            </div>
          </div>
        </div>

        {/* TP2 (optional, 单行展开，避免占满3列时挤压) */}
        {tp2 != null && (
          <div className="flex items-center justify-between text-xs px-1">
            <span className="text-text-tertiary">TP2（远端止盈）</span>
            <span className="font-mono font-semibold text-bull tabular-nums">
              {tp2.toFixed(2)}
            </span>
          </div>
        )}

        {/* ── Row 4: CTA 跟单按钮（主行动） ───────────────────────────── */}
        <button
          onClick={() => setFollowOpen(true)}
          data-testid={`follow-btn-${item.pair}-${timeframe}`}
          className={cn(
            "w-full py-3 rounded-xl text-base font-bold tracking-wide",
            "transition-all active:scale-[0.98]",
            isLong
              ? "bg-bull text-black hover:brightness-110"
              : "bg-bear text-white hover:brightness-110",
          )}
        >
          跟单 {isLong ? "做多" : "做空"} →
        </button>

        {/* FollowDialog：卡片内直接管理 */}
        <FollowDialog
          isOpen={followOpen}
          onClose={() => setFollowOpen(false)}
          pair={okxPair}
          timeframe={timeframe}
          direction={signal.direction}
          recommendedLeverage={leverage}
          entryLevels={signal.entry_levels}
          stopLossPrice={signal.stop_loss_price}
          takeProfit1Price={signal.take_profit_1_price}
          takeProfit2Price={signal.take_profit_2_price}
          atr={signal.atr}
          riskRewardRatio={signal.risk_reward_ratio}
          quality={signal.quality}
        />

        {/* ── Row 5: 微信息（时间戳，市态置信） ───────────────────────── */}
        <div className="flex items-center justify-between text-[11px] text-text-tertiary pt-1">
          <span>
            市态置信{" "}
            {signal.regime_confidence > 0
              ? `${(signal.regime_confidence * 100).toFixed(0)}%`
              : "—"}
          </span>
          <span className="tabular-nums">
            {new Date(signal.generated_at).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>
      </CardBody>
    </Card>
  );
}

// ─── Follow Button (legacy — 已合并进 EnhancedSignalCard 内联) ────────────────
// (代码已内联到 EnhancedSignalCard，保留此 marker 以便 git history)
// ──────────────────────────────────────────────────────────────────────────────
