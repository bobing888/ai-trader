/**
 * AnalysisPanel — 4 大类量化指标（regime / trend / volatility / statistical / multifactor）
 * 用于 K 线页面下方 / 任意 symbol context 周围
 */

import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Brain, Gauge, Sparkles, TrendingUp } from "lucide-react";

import { fetchAnalysis } from "@/lib/api";
import { useSymbolContext } from "@/stores/symbolContextStore";
import { cn } from "@/lib/utils";

interface AnalysisPanelProps {
  fallbackSymbol?: string;
}

export function AnalysisPanel({ fallbackSymbol = "BTCUSDT" }: AnalysisPanelProps) {
  const ctx = useSymbolContext();
  const symbol = ctx.symbol || fallbackSymbol;
  const timeframe = ctx.timeframe || "1h";

  const { data, isLoading, error } = useQuery({
    queryKey: ["analysis", symbol, timeframe],
    queryFn: () => fetchAnalysis(symbol, timeframe, 500),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (!ctx.symbol) {
    return (
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-6 text-center text-text-tertiary text-sm">
        量化分析等待 K 线数据…打开 K 线页面激活。
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-6 text-center text-text-tertiary text-sm">
        计算 4 类量化指标中…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-6 text-center text-text-tertiary text-sm">
        分析失败：{(error as Error).message}
      </div>
    );
  }
  if (!data) return null;

  return (
    <section className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden">
      <header className="flex items-center justify-between gap-2 px-5 py-3 border-b border-[rgba(255,240,220,0.06)]">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-text-tertiary" />
          <h2 className="text-sm font-medium text-text-primary">量化分析 · 4 大类</h2>
          <span className="text-xs text-text-tertiary">
            {symbol} · {timeframe}
          </span>
        </div>
        <span className="text-[10px] text-text-tertiary tabular-nums">
          {new Date(data.as_of).toLocaleString("zh-CN", { hour12: false })}
        </span>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-px bg-[rgba(255,240,220,0.06)]">
        <RegimeCard info={data.regime} />
        <TrendCard info={data.trend} />
        <VolatilityCard info={data.volatility} />
        <StatisticalCard info={data.statistical} />
        <MultiFactorCard info={data.multifactor} />
      </div>
    </section>
  );
}

// ── Individual cards ─────────────────────────────────────────────────────────

function CardWrap({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof Activity;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-bg-secondary p-4 space-y-2 min-h-[160px]">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-text-tertiary font-semibold">
        <Icon className="w-3 h-3" />
        {title}
      </div>
      {children}
    </div>
  );
}

function RegimeCard({ info }: { info: { regime: string; confidence: number; regime_probs: Record<string, number>; description: string } }) {
  const regimeColor = {
    bull: "text-bull",
    bear: "text-bear",
    choppy: "text-warning",
    crisis: "text-danger",
  }[info.regime] ?? "text-text-secondary";

  return (
    <CardWrap title="市场状态 Regime" icon={Activity}>
      <div className="space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className={cn("text-2xl font-semibold tracking-tight", regimeColor)}>
            {info.regime.toUpperCase()}
          </span>
          <span className="text-[11px] text-text-tertiary tabular-nums">
            {Math.round(info.confidence * 100)}%
          </span>
        </div>
        <p className="text-[11px] text-text-tertiary leading-snug">{info.description}</p>
        <div className="space-y-0.5 pt-1">
          {Object.entries(info.regime_probs).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 text-[10px]">
              <span className="w-12 text-text-tertiary">{k}</span>
              <div className="flex-1 h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
                <div
                  className={cn("h-full rounded-full", k === "bull" ? "bg-bull" : k === "bear" ? "bg-bear" : k === "crisis" ? "bg-danger" : "bg-warning")}
                  style={{ width: `${v * 100}%` }}
                />
              </div>
              <span className="w-8 text-right tabular-nums text-text-secondary">{(v * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </div>
    </CardWrap>
  );
}

function TrendCard({ info }: { info: { adx: number; pdi: number; ndi: number; strength_label: string; direction?: "long" | "short" } }) {
  const dir = info.direction;
  return (
    <CardWrap title="趋势强度 ADX" icon={TrendingUp}>
      <div className="space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums tracking-tight">{info.adx.toFixed(1)}</span>
          <span className={cn(
            "text-[11px] px-1.5 py-0.5 rounded-md font-medium",
            dir === "long" ? "bg-bull/10 text-bull" : dir === "short" ? "bg-bear/10 text-bear" : "bg-bg-tertiary text-text-tertiary"
          )}>
            {info.strength_label}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-lg bg-bull/5 p-2">
            <p className="text-[9px] text-text-tertiary uppercase tracking-wider">+DI</p>
            <p className="text-sm font-semibold text-bull tabular-nums">{info.pdi.toFixed(1)}</p>
          </div>
          <div className="rounded-lg bg-bear/5 p-2">
            <p className="text-[9px] text-text-tertiary uppercase tracking-wider">-DI</p>
            <p className="text-sm font-semibold text-bear tabular-nums">{info.ndi.toFixed(1)}</p>
          </div>
        </div>
      </div>
    </CardWrap>
  );
}

function VolatilityCard({ info }: { info: { current_atr_pct: number; percentile_1y: number; level: string } }) {
  const pct = info.percentile_1y;
  const pctColor = pct < 0.3 ? "text-bull" : pct < 0.7 ? "text-warning" : "text-danger";
  return (
    <CardWrap title="波动率分位" icon={BarChart3}>
      <div className="space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className={cn("text-2xl font-semibold tabular-nums tracking-tight", pctColor)}>
            {(pct * 100).toFixed(0)}
            <span className="text-sm font-normal text-text-tertiary ml-0.5">%</span>
          </span>
          <span className="text-[11px] text-text-tertiary">{info.level}</span>
        </div>
        <div>
          <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">当前 ATR</p>
          <p className="text-base font-medium tabular-nums">{(info.current_atr_pct * 100).toFixed(3)}%</p>
        </div>
        <div className="relative h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
          <div
            className={cn("absolute top-0 bottom-0 left-0 rounded-full transition-all",
              pct < 0.3 ? "bg-bull" : pct < 0.7 ? "bg-warning" : "bg-danger"
            )}
            style={{ width: `${pct * 100}%` }}
          />
        </div>
      </div>
    </CardWrap>
  );
}

function StatisticalCard({ info }: { info: { hurst: number; fractal_dim: number; entropy: number; interpretation: string } }) {
  const hurstColor = info.hurst < 0.45 ? "text-bull" : info.hurst > 0.55 ? "text-warning" : "text-text-secondary";
  return (
    <CardWrap title="统计套利 H/F/E" icon={Brain}>
      <div className="space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className={cn("text-2xl font-semibold tabular-nums tracking-tight", hurstColor)}>
            {info.hurst.toFixed(2)}
          </span>
          <span className="text-[11px] text-text-tertiary">Hurst</span>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[10px]">
          <div>
            <p className="text-text-tertiary">分形维数</p>
            <p className="text-sm font-semibold text-text-primary tabular-nums">{info.fractal_dim.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-text-tertiary">Shannon 熵</p>
            <p className="text-sm font-semibold text-text-primary tabular-nums">{info.entropy.toFixed(2)}</p>
          </div>
        </div>
        <p className="text-[10px] text-text-tertiary leading-snug">{info.interpretation}</p>
      </div>
    </CardWrap>
  );
}

function MultiFactorCard({ info }: { info: { technical: number; fundamental: number; sentiment: number; composite: number } }) {
  const compositeColor = info.composite >= 60 ? "text-bull" : info.composite <= 40 ? "text-bear" : "text-warning";
  return (
    <CardWrap title="多因子合成" icon={Gauge}>
      <div className="space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className={cn("text-2xl font-semibold tabular-nums tracking-tight", compositeColor)}>
            {info.composite.toFixed(0)}
          </span>
          <span className="text-[11px] text-text-tertiary">综合分</span>
        </div>
        <div className="space-y-1 pt-1">
          <FactorBar label="技术面" value={info.technical} />
          <FactorBar label="基本面" value={info.fundamental} muted={info.fundamental === 50} />
          <FactorBar label="情绪面" value={info.sentiment} />
        </div>
      </div>
    </CardWrap>
  );
}

function FactorBar({ label, value, muted = false }: { label: string; value: number; muted?: boolean }) {
  const color = value >= 60 ? "bg-bull" : value <= 40 ? "bg-bear" : "bg-warning";
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="w-12 text-text-tertiary shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", muted ? "bg-text-tertiary/40" : color)}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="w-8 text-right tabular-nums text-text-secondary">{value.toFixed(0)}</span>
    </div>
  );
}
