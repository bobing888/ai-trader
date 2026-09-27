/**
 * ConfluenceScoreGauge — 多指标共振分可视化弧形环 (0–100)。
 * 纯 SVG + Tailwind CSS 实现，无新依赖。
 */

import { Badge } from "@/components/ui/Badge";
import { ConfluenceDirectionBadge } from "./ConfluenceDirectionBadge";
import type { ConfluenceInfo } from "@/lib/api";

// ── Color helpers ─────────────────────────────────────────────────────────────

function scoreColor(pct: number): string {
  if (pct >= 80) return "#4ade80"; // bright green
  if (pct >= 60) return "#22d3ee"; // cyan-teal
  if (pct >= 40) return "#facc15"; // yellow
  return "#f87171"; // red
}

function scoreLabel(pct: number): string {
  if (pct >= 80) return "极强共振";
  if (pct >= 60) return "强共振";
  if (pct >= 40) return "中等共振";
  return "弱信号";
}

// ── Arc path helper ──────────────────────────────────────────────────────────
// Draws a circular arc from startAngle → endAngle (in degrees) on a circle of
// radius r centered at (cx, cy). strokeWidth controls the ring thickness.

function polarToXY(cx: number, cy: number, r: number, angleDeg: number): [number, number] {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

function arcPath(
  cx: number, cy: number, r: number,
  startDeg: number, endDeg: number,
): string {
  const [x1, y1] = polarToXY(cx, cy, r, startDeg);
  const [x2, y2] = polarToXY(cx, cy, r, endDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
}

// ── Badge tone mapping ────────────────────────────────────────────────────────

function rsiTone(zone: ConfluenceInfo["rsi14"]["zone"]) {
  if (zone === "overbought") return "warning" as const;
  if (zone === "oversold") return "bull" as const;
  return "info" as const;
}

function adxTone(adx: number) {
  if (adx >= 25) return "bull" as const;
  if (adx >= 15) return "info" as const;
  return "muted" as const;
}

// ── MACD status label ─────────────────────────────────────────────────────────

const MACD_LABELS: Record<ConfluenceInfo["macd"]["status"], string> = {
  bullish_cross: "MACD 金叉",
  bearish_cross: "MACD 死叉",
  above_zero: "MACD 零轴上",
  below_zero: "MACD 零轴下",
};

// ── Component ──────────────────────────────────────────────────────────────────

interface Props {
  confluence: ConfluenceInfo;
}

export function ConfluenceScoreGauge({ confluence }: Props) {
  if (!confluence) return null;

  const { confluence_score, price_vs_ma30, macd, rsi14, adx14, volume_ratio } = confluence;

  const score = Math.round(confluence_score);
  const color = scoreColor(score);
  const label = scoreLabel(score);

  // Ring dimensions
  const SIZE = 140;
  const CX = SIZE / 2;
  const CY = SIZE / 2;
  const R = 52;
  const SW = 10; // stroke width

  // Arc spans -90° → 270° (full 360° sweep), score fills clockwise from top
  const START = -90;
  const FULL = 360;
  const filled = (score / 100) * FULL;
  const endDeg = START + filled;

  const trackPath = arcPath(CX, CY, R, START, START + FULL);
  const fillPath = endDeg > START ? arcPath(CX, CY, R, START, endDeg) : "";

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Direction badge + title */}
      <div className="flex flex-col items-center gap-1">
        <ConfluenceDirectionBadge
          direction={confluence.signal_direction ?? "mixed"}
          score={confluence.confluence_score}
        />
        <span className="text-[9px] text-text-tertiary uppercase tracking-widest">多指标共识 · 方向</span>
      </div>

      {/* SVG Arc */}
      <div className="relative">
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="-rotate-90"
        >
          {/* Track ring */}
          <path
            d={trackPath}
            fill="none"
            stroke="rgba(255,240,220,0.06)"
            strokeWidth={SW}
            strokeLinecap="round"
          />
          {/* Filled arc */}
          {fillPath && (
            <path
              d={fillPath}
              fill="none"
              stroke={color}
              strokeWidth={SW}
              strokeLinecap="round"
              className="transition-all duration-700"
            />
          )}
        </svg>

        {/* Score + label overlay */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="text-3xl font-black tabular-nums leading-none"
            style={{ color }}
          >
            {score}
          </span>
          <span
            className="text-[10px] font-semibold mt-0.5 tracking-wide"
            style={{ color }}
          >
            {label}
          </span>
        </div>
      </div>

      {/* Indicator badges */}
      <div className="flex flex-wrap justify-center gap-1.5 max-w-[160px]">
        {/* MA30 */}
        <Badge
          tone={
            price_vs_ma30 === "above" || price_vs_ma30 === "cross_above"
              ? "bull"
              : price_vs_ma30 === "cross_below"
              ? "warning"
              : "bear"
          }
        >
          MA30 {price_vs_ma30.replace("_", " ")}
        </Badge>

        {/* MACD */}
        <Badge
          tone={
            macd.status === "bullish_cross" || macd.status === "above_zero"
              ? "bull"
              : "bear"
          }
        >
          {MACD_LABELS[macd.status]}
        </Badge>

        {/* RSI */}
        <Badge tone={rsiTone(rsi14.zone)}>
          RSI14 {rsi14.value.toFixed(0)} {rsi14.zone === "overbought" ? "超买" : rsi14.zone === "oversold" ? "超卖" : "中性"}
        </Badge>

        {/* ADX */}
        <Badge tone={adxTone(adx14.adx)}>
          ADX {adx14.adx.toFixed(1)}
        </Badge>

        {/* Volume ratio */}
        <Badge tone={volume_ratio >= 1.5 ? "bull" : volume_ratio <= 0.7 ? "bear" : "default"}>
          Vol ×{volume_ratio.toFixed(1)}
        </Badge>
      </div>
    </div>
  );
}
