import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { EquityPoint } from "@/lib/equity";

export interface EquityCurveProps {
  points: EquityPoint[];
  height?: number;
  className?: string;
}

interface Padding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

const PADDING: Padding = { top: 16, right: 16, bottom: 24, left: 48 };

/** Robinhood-style animated equity curve with hover crosshair + tooltip. */
export function EquityCurve({ points, height = 220, className }: EquityCurveProps) {
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(800);

  // Track container width
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(e.contentRect.width);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const isEmpty = points.length < 2;
  const isProfit = points.length > 0 && points[points.length - 1].cumulative >= 0;
  const accentClass = isProfit ? "text-bull" : "text-bear";
  const strokeColor = isProfit ? "var(--color-bull)" : "var(--color-bear)";
  const gradientId = `equity-gradient-${isProfit ? "bull" : "bear"}`;

  const { path, areaPath, xTicks, yTicks } = useMemo(() => {
    if (isEmpty) {
      return { path: "", areaPath: "", xTicks: [], yTicks: [] };
    }

    const innerW = width - PADDING.left - PADDING.right;
    const innerH = height - PADDING.top - PADDING.bottom;

    const xs = points.map((_, i) => i);
    const ys = points.map((p) => p.cumulative);
    const minX = 0;
    const maxX = xs.length - 1;
    const minY = Math.min(...ys, 0);
    const maxY = Math.max(...ys, 0);
    const yRange = Math.max(maxY - minY, 1);

    const xAt = (i: number) => PADDING.left + ((i - minX) / Math.max(maxX - minX, 1)) * innerW;
    const yAt = (v: number) => PADDING.top + (1 - (v - minY) / yRange) * innerH;

    // Build smooth path with simple line segments
    let linePath = `M ${xAt(0)} ${yAt(points[0].cumulative)}`;
    for (let i = 1; i < points.length; i++) {
      linePath += ` L ${xAt(i)} ${yAt(points[i].cumulative)}`;
    }
    // Close to baseline for area fill
    const baseY = yAt(Math.max(minY, 0));
    const lastX = xAt(maxX);
    const firstX = xAt(0);
    const fillPath = `${linePath} L ${lastX} ${baseY} L ${firstX} ${baseY} Z`;

    // X ticks: 5 evenly spaced points (dates)
    const tickCount = 4;
    const xTickArr = Array.from({ length: tickCount + 1 }, (_, i) => {
      const idx = Math.round((maxX * i) / tickCount);
      return { idx, x: xAt(idx), time: points[idx]?.time };
    });

    // Y ticks: 4 evenly spaced
    const yTickArr = Array.from({ length: 5 }, (_, i) => {
      const value = minY + (yRange * i) / 4;
      return { value, y: yAt(value) };
    });

    return { path: linePath, areaPath: fillPath, xTicks: xTickArr, yTicks: yTickArr };
  }, [points, width, height, isEmpty]);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (isEmpty) return;
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const innerW = width - PADDING.left - PADDING.right;
    const ratio = (e.clientX - rect.left - PADDING.left) / innerW;
    if (ratio < 0 || ratio > 1) {
      setActiveIdx(null);
      return;
    }
    const idx = Math.round(ratio * (points.length - 1));
    setActiveIdx(Math.max(0, Math.min(points.length - 1, idx)));
  };

  const handleMouseLeave = () => setActiveIdx(null);

  const activePoint = activeIdx !== null ? points[activeIdx] : null;
  const activeX = activeIdx !== null
    ? PADDING.left + (activeIdx / Math.max(points.length - 1, 1)) * (width - PADDING.left - PADDING.right)
    : 0;

  const fmtTime = (iso: string) => {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const fmtCum = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(2);

  return (
    <div ref={containerRef} className={cn("relative w-full", className)}>
      {isEmpty ? (
        <div
          className="flex items-center justify-center text-sm text-text-tertiary"
          style={{ height }}
        >
          数据不足，先去下单至少 2 笔成交后再来看曲线
        </div>
      ) : (
        <svg
          width={width}
          height={height}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          className="select-none"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.35" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Y-axis grid + labels */}
          {yTicks.map((t, i) => (
            <g key={`y-${i}`}>
              <line
                x1={PADDING.left}
                y1={t.y}
                x2={width - PADDING.right}
                y2={t.y}
                stroke="rgba(255,240,220,0.05)"
                strokeDasharray="2 4"
              />
              <text
                x={PADDING.left - 8}
                y={t.y + 3}
                textAnchor="end"
                className="fill-text-tertiary"
                style={{ fontSize: 10, fontVariantNumeric: "tabular-nums" }}
              >
                {t.value >= 0 ? "+" : ""}
                {t.value.toFixed(0)}
              </text>
            </g>
          ))}

          {/* Zero baseline emphasized */}
          {yTicks.length > 0 && (() => {
            const minY = Math.min(...points.map((p) => p.cumulative), 0);
            const maxY = Math.max(...points.map((p) => p.cumulative), 0);
            const yRange = Math.max(maxY - minY, 1);
            const innerH = height - PADDING.top - PADDING.bottom;
            const yZero = PADDING.top + (1 - (0 - minY) / yRange) * innerH;
            return (
              <line
                x1={PADDING.left}
                y1={yZero}
                x2={width - PADDING.right}
                y2={yZero}
                stroke="rgba(255,240,220,0.15)"
                strokeWidth={1}
              />
            );
          })()}

          {/* Area fill */}
          <path d={areaPath} fill={`url(#${gradientId})`} />

          {/* Line */}
          <path
            d={path}
            fill="none"
            stroke={strokeColor}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            className="drop-shadow-[0_0_8px_var(--color-bull)]"
          />

          {/* X-axis labels */}
          {xTicks.map((t, i) => (
            <text
              key={`x-${i}`}
              x={t.x}
              y={height - 6}
              textAnchor="middle"
              className="fill-text-tertiary"
              style={{ fontSize: 10 }}
            >
              {t.time ? fmtTime(t.time) : ""}
            </text>
          ))}

          {/* Crosshair */}
          {activePoint && (
            <g>
              <line
                x1={activeX}
                y1={PADDING.top}
                x2={activeX}
                y2={height - PADDING.bottom}
                stroke="rgba(255,240,220,0.2)"
                strokeDasharray="3 3"
              />
              <circle
                cx={activeX}
                cy={(() => {
                  const minY = Math.min(...points.map((p) => p.cumulative), 0);
                  const maxY = Math.max(...points.map((p) => p.cumulative), 0);
                  const yRange = Math.max(maxY - minY, 1);
                  const innerH = height - PADDING.top - PADDING.bottom;
                  return PADDING.top + (1 - (activePoint.cumulative - minY) / yRange) * innerH;
                })()}
                r={4}
                fill={strokeColor}
                stroke="#0d0d0d"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>
      )}

      {/* Tooltip (positioned outside SVG so it can use HTML) */}
      {activePoint && !isEmpty && (
        <div
          className="pointer-events-none absolute top-2 right-3 rounded-xl bg-bg-tertiary border border-[rgba(255,240,220,0.1)] px-3 py-2 text-xs shadow-xl backdrop-blur"
        >
          <div className="text-text-tertiary mb-0.5 tabular-nums">
            {new Date(activePoint.time).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
          </div>
          <div className={cn("font-semibold tabular-nums", accentClass)}>
            累计 {fmtCum(activePoint.cumulative)}
          </div>
          <div className="text-text-secondary tabular-nums mt-0.5">
            +{activePoint.pair}: {fmtCum(activePoint.tradeProfit)}
          </div>
        </div>
      )}
    </div>
  );
}
