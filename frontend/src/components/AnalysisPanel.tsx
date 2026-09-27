/**
 * AnalysisPanel — 4 大类量化指标（regime / trend / volatility / statistical / multifactor）
 * 用于 K 线页面下方 / 任意 symbol context 周围。
 *
 * Layout:
 *  - Left half: multifactor radar chart (technical / fundamental / sentiment, 3-axis SVG)
 *  - Right half: composite big number + bull/bear indicator bar
 *  - Below: trend / volatility / statistical cards (secondary)
 */

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Brain, Sparkles, TrendingUp } from "lucide-react";

import { fetchAnalysis } from "@/lib/api";
import { useSymbolContext } from "@/stores/symbolContextStore";
import { cn } from "@/lib/utils";

interface AnalysisPanelProps {
  fallbackSymbol?: string;
}

// ── Radar chart (pure SVG, 3-axis) ───────────────────────────────────────────

function MultifactorRadar({
  technical,
  fundamental,
  sentiment,
}: {
  technical: number;
  fundamental: number;
  sentiment: number;
}) {
  const size = 200;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = 80;

  // 3 axes at 0°, 120°, 240° (clockwise)
  const axes = [
    { label: "技术面", value: technical, angleDeg: -90 },
    { label: "基本面", value: fundamental, angleDeg: 30 },
    { label: "情绪面", value: sentiment, angleDeg: 150 },
  ];

  // Points for the data polygon
  const dataPoints = axes.map((a) => {
    const r = (a.value / 100) * maxR;
    const rad = (a.angleDeg * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(rad),
      y: cy + r * Math.sin(rad),
    };
  });

  const polyFill = dataPoints.map((p) => `${p.x},${p.y}`).join(" ");

  // Grid rings at 25%, 50%, 75%, 100%
  const rings = [0.25, 0.5, 0.75, 1.0].map((frac) => {
    const r = frac * maxR;
    return axes.map((a) => {
      const rad = (a.angleDeg * Math.PI) / 180;
      return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
    }).map((p) => `${p.x},${p.y}`).join(" ");
  });

  // Axis lines
  const axisLines = axes.map((a) => {
    const rad = (a.angleDeg * Math.PI) / 180;
    return {
      x1: cx,
      y1: cy,
      x2: cx + maxR * Math.cos(rad),
      y2: cy + maxR * Math.sin(rad),
    };
  });

  // Axis label positions (slightly outside)
  const labelPositions = axes.map((a) => {
    const rad = (a.angleDeg * Math.PI) / 180;
    const r = maxR + 18;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) + 4 };
  });

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="overflow-visible"
      aria-label="多因子雷达图"
    >
      {/* Grid rings */}
      {rings.map((pts, i) => (
        <polygon key={i} points={pts} fill="none" stroke="rgba(255,240,220,0.06)" strokeWidth="1" />
      ))}

      {/* Axis lines */}
      {axisLines.map((l, i) => (
        <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="rgba(255,240,220,0.1)" strokeWidth="1" />
      ))}

      {/* Data fill */}
      <polygon
        points={polyFill}
        fill="rgba(74,222,128,0.15)"
        stroke="rgba(74,222,128,0.6)"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />

      {/* Data points */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="rgba(74,222,128,0.9)" />
      ))}

      {/* Axis labels */}
      {axes.map((a, i) => {
        const pos = labelPositions[i];
        const anchor = a.angleDeg === -90 ? "middle" : a.angleDeg === 30 ? "start" : "end";
        return (
          <text
            key={i}
            x={pos.x}
            y={pos.y}
            textAnchor={anchor}
            className="fill-text-tertiary text-[10px] font-medium"
          >
            {a.label}
          </text>
        );
      })}

      {/* Value labels */}
      {dataPoints.map((p, i) => (
        <text
          key={i}
          x={p.x}
          y={p.y - 8}
          textAnchor="middle"
          className="fill-text-primary text-[10px] font-semibold"
        >
          {axes[i].value.toFixed(0)}
        </text>
      ))}
    </svg>
  );
}

// ── Composite gauge ───────────────────────────────────────────────────────────

function CompositeGauge({ composite }: { composite: number }) {
  const score = composite;
  const color =
    score >= 60 ? "#4ade80" : score <= 40 ? "#f87171" : "#facc15";
  const label =
    score >= 60 ? "偏多" : score <= 40 ? "偏空" : "中性";

  // Indicator bar: center = 50, fill left or right from center
  const fillPct = Math.abs(score - 50);

  return (
    <div className="flex flex-col items-center gap-3 w-full">
      {/* Big number */}
      <div className="flex items-baseline gap-1">
        <span className="text-6xl font-black tabular-nums tracking-tight" style={{ color }}>
          {score.toFixed(0)}
        </span>
        <span className="text-lg text-text-tertiary font-medium">分</span>
      </div>

      {/* Indicator bar */}
      <div className="w-full max-w-[220px]">
        <div className="relative h-3 rounded-full bg-bg-tertiary overflow-hidden">
          {/* Center marker */}
          <div className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-px bg-[rgba(255,240,220,0.2)]" />

          {/* Fill: green on right (bull) or red on left (bear) */}
          {score >= 50 ? (
            <div
              className="absolute top-0 bottom-0 left-1/2 rounded-r-full transition-all duration-700"
              style={{ width: `${fillPct}%`, background: color }}
            />
          ) : (
            <div
              className="absolute top-0 bottom-0 right-1/2 rounded-l-full transition-all duration-700"
              style={{ width: `${fillPct}%`, background: color }}
            />
          )}
        </div>
        <div className="flex justify-between mt-1.5">
          <span className="text-[10px] text-bear font-medium">0</span>
          <span
            className="text-[10px] font-semibold tabular-nums"
            style={{ color }}
          >
            {label}
          </span>
          <span className="text-[10px] text-bull font-medium">100</span>
        </div>
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

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
          <h2 className="text-sm font-medium text-text-primary">量化分析</h2>
          <span className="text-xs text-text-tertiary">
            {symbol} · {timeframe}
          </span>
        </div>
        <span className="text-[10px] text-text-tertiary tabular-nums">
          {new Date(data.as_of).toLocaleString("zh-CN", { hour12: false })}
        </span>
      </header>

      {/* Multifactor highlight: radar + composite */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-0 border-b border-[rgba(255,240,220,0.06)]">
        {/* Radar */}
        <div className="flex flex-col items-center justify-center p-6 border-r border-[rgba(255,240,220,0.06)]">
          <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-3">多因子雷达</p>
          <MultifactorRadar
            technical={data.multifactor.technical}
            fundamental={data.multifactor.fundamental}
            sentiment={data.multifactor.sentiment}
          />
        </div>

        {/* Composite gauge */}
        <div className="flex flex-col items-center justify-center p-6">
          <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-3">综合评分</p>
          <CompositeGauge composite={data.multifactor.composite} />
        </div>
      </div>

      {/* Secondary cards: trend / volatility / statistical */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-0">
        <TrendCard info={data.trend} />
        <VolatilityCard info={data.volatility} />
        <StatisticalCard info={data.statistical} />
      </div>
    </section>
  );
}

// ── Secondary cards ────────────────────────────────────────────────────────────

function TrendCard({ info }: { info: { adx: number; pdi: number; ndi: number; strength_label: string; direction?: "long" | "short" } }) {
  const dir = info.direction;
  return (
    <div className="p-4 border-r border-[rgba(255,240,220,0.06)] min-h-[140px]">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-2">
        <TrendingUp className="w-3 h-3" />
        趋势强度 ADX
      </div>
      <div className="space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums tracking-tight text-text-primary">
            {info.adx.toFixed(1)}
          </span>
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
    </div>
  );
}

function VolatilityCard({ info }: { info: { current_atr_pct: number; percentile_1y: number; level: string } }) {
  const pct = info.percentile_1y;
  const pctColor = pct < 0.3 ? "text-bull" : pct < 0.7 ? "text-warning" : "text-danger";
  return (
    <div className="p-4 border-r border-[rgba(255,240,220,0.06)] min-h-[140px]">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-2">
        <BarChart3 className="w-3 h-3" />
        波动率分位
      </div>
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
          <p className="text-base font-medium tabular-nums text-text-primary">{(info.current_atr_pct * 100).toFixed(3)}%</p>
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
    </div>
  );
}

function StatisticalCard({ info }: { info: { hurst: number; fractal_dim: number; entropy: number; interpretation: string } }) {
  const hurstColor = info.hurst < 0.45 ? "text-bull" : info.hurst > 0.55 ? "text-warning" : "text-text-secondary";
  return (
    <div className="p-4 min-h-[140px]">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-2">
        <Brain className="w-3 h-3" />
        统计套利 H/F/E
      </div>
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
    </div>
  );
}
