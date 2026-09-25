import type { LineDataPoint } from "@/lib/equityCurve";

export interface EquityCurveProps {
  data: LineDataPoint[];
  height?: number;
}

// Pure SVG line chart — no external dep. Renders smooth path with gradient fill.
export function EquityCurve({ data, height = 200 }: EquityCurveProps) {
  if (data.length < 2) {
    return (
      <div className="flex items-center justify-center text-text-tertiary text-sm" style={{ height }}>
        数据不足
      </div>
    );
  }

  const padding = { top: 16, right: 12, bottom: 24, left: 48 };
  const width = 800; // viewBox width — auto-scales via SVG preserveAspectRatio
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const values = data.map((d) => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const x = (i: number) => padding.left + (i / (data.length - 1)) * innerW;
  const y = (v: number) => padding.top + innerH - ((v - min) / range) * innerH;

  const points = data.map((d, i) => ({ x: x(i), y: y(d.value) }));

  // Smooth path using Catmull-Rom-ish cubic Bezier
  const path = points.reduce((acc, p, i, arr) => {
    if (i === 0) return `M ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    const prev = arr[i - 1];
    const cx = (prev.x + p.x) / 2;
    return `${acc} Q ${prev.x.toFixed(2)} ${prev.y.toFixed(2)} ${cx.toFixed(2)} ${((prev.y + p.y) / 2).toFixed(2)} T ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
  }, "");

  const areaPath = `${path} L ${points[points.length - 1].x.toFixed(2)} ${(padding.top + innerH).toFixed(2)} L ${points[0].x.toFixed(2)} ${(padding.top + innerH).toFixed(2)} Z`;

  const lastValue = values[values.length - 1];
  const firstValue = values[0];
  const positive = lastValue >= firstValue;
  const stroke = positive ? "#22c55e" : "#ef4444";
  const gradientId = `eq-grad-${positive ? "bull" : "bear"}`;

  // Y-axis ticks (4 evenly spaced)
  const yTicks = Array.from({ length: 4 }, (_, i) => {
    const v = min + (range * i) / 3;
    return { v, y: y(v) };
  });

  // X-axis ticks (5 evenly spaced)
  const xTicks = Array.from({ length: 5 }, (_, i) => {
    const idx = Math.floor((i / 4) * (data.length - 1));
    return { label: data[idx].label, x: x(idx) };
  });

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="w-full"
      style={{ height }}
      role="img"
      aria-label="Equity curve"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.25" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yTicks.map((t, i) => (
        <line
          key={`grid-${i}`}
          x1={padding.left}
          y1={t.y}
          x2={width - padding.right}
          y2={t.y}
          stroke="rgba(255, 240, 220, 0.06)"
          strokeWidth="1"
        />
      ))}

      {/* Y axis labels */}
      {yTicks.map((t, i) => (
        <text
          key={`yl-${i}`}
          x={padding.left - 8}
          y={t.y + 3}
          fill="rgba(255, 240, 220, 0.42)"
          fontSize="10"
          textAnchor="end"
          fontFamily="Inter, sans-serif"
        >
          {formatNumber(t.v)}
        </text>
      ))}

      {/* X axis labels */}
      {xTicks.map((t, i) => (
        <text
          key={`xl-${i}`}
          x={t.x}
          y={height - 6}
          fill="rgba(255, 240, 220, 0.42)"
          fontSize="10"
          textAnchor="middle"
          fontFamily="Inter, sans-serif"
        >
          {t.label}
        </text>
      ))}

      {/* Area fill */}
      <path d={areaPath} fill={`url(#${gradientId})`} />

      {/* Line */}
      <path d={path} fill="none" stroke={stroke} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

      {/* End point dot */}
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r="3.5"
        fill={stroke}
        stroke="#140c0c"
        strokeWidth="2"
      />
    </svg>
  );
}

function formatNumber(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toFixed(0);
}
