/**
 * AICoreVerdictBanner — 顶部大字 AI 核心判读区。
 * 展示 regime 大标签、综合置信度环形进度、AI 整体建议。
 */

import { AlertTriangle, Minus, TrendingDown, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { ConfluenceScoreGauge } from "@/components/analysis/ConfluenceScoreGauge";
import { cn } from "@/lib/utils";
import type { AnalysisResponse } from "@/lib/api";

interface Props {
  data: AnalysisResponse;
}

// ── Regime → Chinese label ────────────────────────────────────────────────────

const REGIME_LABELS: Record<string, string> = {
  bull: "强势多头",
  bear: "强势空头",
  choppy: "震荡洗盘",
  crisis: "极端波动",
};

const REGIME_COLORS: Record<string, string> = {
  bull: "text-bull",
  bear: "text-bear",
  choppy: "text-warning",
  crisis: "text-danger",
};

const REGIME_BG: Record<string, string> = {
  bull: "bg-bull/10 border-bull/20",
  bear: "bg-bear/10 border-bear/20",
  choppy: "bg-warning/10 border-warning/20",
  crisis: "bg-danger/10 border-danger/20",
};

const REGIME_ICON: Record<string, typeof TrendingUp> = {
  bull: TrendingUp,
  bear: TrendingDown,
  choppy: Minus,
  crisis: AlertTriangle,
};

// ── AI advice logic ──────────────────────────────────────────────────────────

function buildAdvice(regimeName: string, composite: number): string {
  if (regimeName === "crisis") {
    return "极端波动，降低杠杆，等待企稳";
  }
  if (composite >= 60 && regimeName === "bull") {
    return "顺势做多，关注突破";
  }
  if (composite >= 60 && regimeName === "bear") {
    return "反弹做空优于抄底";
  }
  if (composite <= 40 && regimeName === "bull") {
    return "回调企稳做多";
  }
  if (composite <= 40 && regimeName === "bear") {
    return "顺势做空，严控仓位";
  }
  return "多空均衡，观望等待突破";
}

// ── Confidence ring (SVG) ────────────────────────────────────────────────────

function ConfidenceRing({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const R = 28;
  const C = 2 * Math.PI * R;
  const dash = (C * pct) / 100;
  const gap = C - dash;

  const color =
    pct >= 70 ? "#4ade80" : pct >= 40 ? "#facc15" : "#f87171";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="72" height="72" viewBox="0 0 72 72" className="-rotate-90">
        {/* Track */}
        <circle
          cx="36" cy="36" r={R}
          fill="none"
          stroke="rgba(255,240,220,0.06)"
          strokeWidth="5"
        />
        {/* Progress */}
        <circle
          cx="36" cy="36" r={R}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${gap}`}
          className="transition-all duration-700"
        />
      </svg>
      <span className="text-[11px] font-semibold tabular-nums" style={{ color }}>
        {pct}%
      </span>
      <span className="text-[9px] text-text-tertiary">置信度</span>
    </div>
  );
}

// ── Banner ───────────────────────────────────────────────────────────────────

export function AICoreVerdictBanner({ data }: Props) {
  const regimeName = data.regime.regime;
  const confidence = data.regime.confidence;
  const composite = data.multifactor.composite;

  const label = REGIME_LABELS[regimeName] ?? regimeName;
  const color = REGIME_COLORS[regimeName] ?? "text-text-primary";
  const bg = REGIME_BG[regimeName] ?? "bg-bg-tertiary border-border-subtle";
  const Icon = REGIME_ICON[regimeName] ?? TrendingUp;
  const advice = buildAdvice(regimeName, composite);

  return (
    <div className={cn(
      "rounded-2xl border px-6 py-5",
      "flex flex-col sm:flex-row items-start sm:items-center gap-5",
      bg,
    )}>
      {/* Left: Regime big label */}
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <div className={cn(
          "w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 border",
          bg,
        )}>
          <Icon className={cn("w-7 h-7", color)} />
        </div>
        <div className="min-w-0">
          <h1 className={cn("text-4xl font-black tracking-tight leading-none", color)}>
            {label}
          </h1>
          <p className="text-sm text-text-secondary mt-1 truncate">
            {data.regime.description}
          </p>
          <Badge
            tone={regimeName === "bull" ? "bull" : regimeName === "bear" ? "bear" : regimeName === "crisis" ? "warning" : "default"}
            className="mt-1.5"
          >
            {regimeName.toUpperCase()}
          </Badge>
        </div>
      </div>

      {/* Right: Confidence ring + advice */}
      <div className="flex items-center gap-5 sm:gap-6 shrink-0">
        {data.trend.confluence && (
          <ConfluenceScoreGauge confluence={data.trend.confluence} />
        )}
        <ConfidenceRing confidence={confidence} />

        <div className="h-12 w-px bg-[rgba(255,240,220,0.1)] hidden sm:block" />

        <div className="flex flex-col gap-1 max-w-[200px]">
          <p className="text-[10px] text-text-tertiary uppercase tracking-wider">AI 整体建议</p>
          <p className="text-sm font-medium text-text-primary leading-snug">{advice}</p>
        </div>
      </div>
    </div>
  );
}
