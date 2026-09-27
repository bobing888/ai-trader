/**
 * AnalysisRegimeCard — 综合判读卡片（替换原 AICoreVerdictBanner）。
 * 简化版：regime 大字 + 一句话建议 + 置信度 + 综合评分，不用环形图。
 */

import { AlertTriangle, Minus, TrendingDown, TrendingUp } from "lucide-react";

import type { AnalysisResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  data: AnalysisResponse;
}

const REGIME_STYLES = {
  bull: {
    label: "强势多头",
    action: "顺势做多，关注突破",
    color: "text-bull",
    bg: "bg-bull/10 border-bull/30",
    icon: TrendingUp,
  },
  bear: {
    label: "强势空头",
    action: "反弹做空优于抄底",
    color: "text-bear",
    bg: "bg-bear/10 border-bear/30",
    icon: TrendingDown,
  },
  choppy: {
    label: "震荡洗盘",
    action: "区间操作，高抛低吸",
    color: "text-warning",
    bg: "bg-warning/10 border-warning/30",
    icon: Minus,
  },
  crisis: {
    label: "极端波动",
    action: "降低杠杆，等待企稳",
    color: "text-danger",
    bg: "bg-danger/10 border-danger/30",
    icon: AlertTriangle,
  },
} as const;

export function AnalysisRegimeCard({ data }: Props) {
  const regimeName = data.regime.regime;
  const style = REGIME_STYLES[regimeName] ?? {
    label: regimeName,
    action: "多空均衡，观望等待突破",
    color: "text-text-secondary",
    bg: "bg-bg-tertiary border-border-subtle",
    icon: Minus,
  };
  const Icon = style.icon;
  const confidence = Math.round(data.regime.confidence * 100);
  const composite = Math.round(data.multifactor.composite);
  const stanceTone =
    composite >= 60 ? "text-bull" : composite <= 40 ? "text-bear" : "text-warning";
  const stanceLabel =
    composite >= 60 ? "偏多" : composite <= 40 ? "偏空" : "中性";

  return (
    <div
      className={cn(
        "rounded-2xl border-2 px-6 py-6 sm:px-8 sm:py-8",
        "flex flex-col lg:flex-row items-start lg:items-center gap-6",
        style.bg,
      )}
    >
      <div className="flex items-center gap-4 flex-1 min-w-0">
        <div
          className={cn(
            "w-16 h-16 rounded-2xl flex items-center justify-center shrink-0 border-2",
            style.bg,
          )}
        >
          <Icon className={cn("w-9 h-9", style.color)} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-widest text-text-tertiary font-semibold mb-1">
            当前市场状态
          </p>
          <p className={cn("text-4xl sm:text-5xl font-black tracking-tight leading-none", style.color)}>
            {style.label}
          </p>
          <p className="text-base sm:text-lg text-text-primary mt-2 leading-snug">
            {style.action}
          </p>
        </div>
      </div>

      <div className="flex items-stretch gap-4 sm:gap-6 shrink-0 w-full lg:w-auto">
        <Metric
          label="置信度"
          value={`${confidence}%`}
          tone={
            confidence >= 70 ? "text-bull" : confidence >= 40 ? "text-warning" : "text-bear"
          }
        />
        <div className="w-px self-stretch bg-[rgba(255,240,220,0.1)]" />
        <Metric label="综合评分" value={`${composite}`} sub={stanceLabel} tone={stanceTone} />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-3 sm:px-4 min-w-[100px]">
      <p className="text-xs uppercase tracking-wider text-text-tertiary font-semibold mb-1">
        {label}
      </p>
      <p className={cn("text-4xl sm:text-5xl font-black tabular-nums tracking-tight", tone)}>
        {value}
      </p>
      {sub && <p className={cn("text-sm font-bold mt-1", tone)}>{sub}</p>}
    </div>
  );
}
