/**
 * AnalysisSummaryBar — 顶页摘要条。
 * 显示: 当前 symbol · timeframe · regime · composite score · AI 建议。
 */

import { ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import type { AnalysisResponse } from "@/lib/api";

interface Props {
  data: AnalysisResponse;
}

const REGIME_LABELS: Record<string, string> = {
  bull: "强势多头",
  bear: "强势空头",
  choppy: "震荡洗盘",
  crisis: "极端波动",
};

const REGIME_TONE: Record<string, "bull" | "bear" | "warning" | "muted"> = {
  bull: "bull",
  bear: "bear",
  choppy: "warning",
  crisis: "warning",
};

function getAdvice(regimeName: string, composite: number): string {
  if (regimeName === "crisis") return "降低杠杆，等待企稳";
  if (composite >= 60 && regimeName === "bull") return "顺势做多";
  if (composite >= 60 && regimeName === "bear") return "反弹做空";
  if (composite <= 40 && regimeName === "bull") return "回调做多";
  if (composite <= 40 && regimeName === "bear") return "顺势做空";
  return "观望等待突破";
}

export function AnalysisSummaryBar({ data }: Props) {
  const { symbol, timeframe } = data;
  const regimeName = data.regime.regime;
  const confidence = data.regime.confidence;
  const composite = data.multifactor.composite;

  const regimeLabel = REGIME_LABELS[regimeName] ?? regimeName;
  const regimeTone = REGIME_TONE[regimeName] ?? "muted";
  const advice = getAdvice(regimeName, composite);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] px-4 py-2.5 text-xs">
      {/* Symbol + timeframe */}
      <span className="font-semibold text-text-primary">{symbol}</span>
      <span className="text-text-tertiary">{timeframe}</span>

      <span className="text-[rgba(255,240,220,0.1)]">·</span>

      {/* Regime badge */}
      <Badge tone={regimeTone}>
        {regimeLabel}
      </Badge>

      <span className="text-[rgba(255,240,220,0.1)]">·</span>

      {/* Confidence */}
      <span className="text-text-secondary">
        置信
        <span className={regimeName === "bull" ? "text-bull" : regimeName === "bear" ? "text-bear" : "text-warning"}>
          {Math.round(confidence * 100)}%
        </span>
      </span>

      <span className="text-[rgba(255,240,220,0.1)]">·</span>

      {/* Composite score */}
      <span className="text-text-secondary">
        综合
        <span className={
          composite >= 60 ? "text-bull font-semibold" :
          composite <= 40 ? "text-bear font-semibold" :
          "text-warning font-semibold"
        }>
          {composite.toFixed(0)}分
        </span>
      </span>

      <span className="text-[rgba(255,240,220,0.1)]">·</span>

      {/* AI advice */}
      <span className="text-text-secondary italic">{advice}</span>

      <ArrowRight className="w-3 h-3 text-text-tertiary ml-auto shrink-0" />
    </div>
  );
}
