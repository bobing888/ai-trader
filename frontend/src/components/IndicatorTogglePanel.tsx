import { cn } from "@/lib/utils";
import type { ChartPreferences } from "@/lib/preferences";
import { MA_BOLL_COLORS } from "@/lib/indicatorColors";

// 把 MA_BOLL_COLORS 提到独立文件后，本文件只剩 React 组件一种 export —
// Vite Fast Refresh 才能热替换（mixed export 触发 full reload，在 KlineChart
// prefs 重 mount 时容易撞 React StrictMode 双调用，导致
// "Rendered more hooks than during the previous render" race）。

interface IndicatorSpec {
  id: string;
  label: string;
  swatch: string;
  /** "solid" | "dashed" — 仅视觉描述 */
  style?: "solid" | "dashed";
  hint?: string;
}

const ROWS: IndicatorSpec[] = [
  { id: "ma5",  label: "MA 5",  swatch: MA_BOLL_COLORS.ma5,  style: "solid", hint: "极短周期" },
  { id: "ma10", label: "MA 10", swatch: MA_BOLL_COLORS.ma10, style: "solid", hint: "短周期" },
  { id: "ma20", label: "MA 20", swatch: MA_BOLL_COLORS.ma20, style: "solid", hint: "中期" },
  { id: "ma30", label: "MA 30", swatch: MA_BOLL_COLORS.ma30, style: "solid", hint: "中期趋势" },
  { id: "ma60", label: "MA 60", swatch: MA_BOLL_COLORS.ma60, style: "solid", hint: "长周期趋势" },
  {
    id: "boll",
    label: "BOLL 布林带",
    swatch: MA_BOLL_COLORS.bollMid,
    style: "dashed",
    hint: "中轨 20 + 上下轨 ±2σ",
  },
];

export interface IndicatorTogglePanelProps {
  prefs: ChartPreferences;
  onChange: (indicatorId: string, enabled: boolean) => void;
}

/**
 * K 线指标 chip 行 — 用户重点关注 MA 系列（5/10/20/30/60）+ BOLL（布林带）。
 * 每个 MA 一个 chip；BOLL 一个 chip 同时控制 3 条线（中轨 + 上下轨）。
 * 渲染：色块（实心/虚线样式）+ 指标名，整块 clickable，点一次切换 on/off。
 * 数据流：组件是纯展示，切换触发 onChange(id, enabled)；
 * 父组件（KlinePage）负责写 prefs 并 reload KlineChart。
 *
 * 与上一版区别：从 K 线图下方卡片 + 右侧 Toggle 开关 → 移到 K 线图正上方，
 * 整体作为 chip 按钮组（横向 row），单个 chip 是一个完整的可点击 button，
 * 视觉上以"显示中"高亮 + 色块，"未显示"降低不透明度，不再嵌外层 Card。
 */
export function IndicatorTogglePanel({ prefs, onChange }: IndicatorTogglePanelProps) {
  return (
    <div
      className="flex flex-row flex-wrap items-center gap-2"
      data-testid="indicator-toggle-panel"
      role="toolbar"
      aria-label="K 线指标切换"
    >
      {ROWS.map((row) => {
        const enabled = !!prefs.indicators[row.id]?.enabled;
        const swatchBg = row.style === "dashed"
          ? `linear-gradient(to bottom, ${row.swatch} 0 3px, transparent 3px 7px, ${row.swatch} 7px 10px)`
          : row.swatch;
        const swatchShadow = row.style === "dashed" ? "none" : `0 0 6px ${row.swatch}55`;
        return (
          <button
            key={row.id}
            type="button"
            aria-pressed={enabled}
            aria-label={`${row.label}（${enabled ? "已显示" : "未显示"}，点击切换）`}
            data-testid={`indicator-toggle-${row.id}`}
            onClick={() => onChange(row.id, !enabled)}
            className={cn(
              "group inline-flex items-center gap-1.5 h-8 px-3 rounded-full",
              "border transition-all duration-150 cursor-pointer select-none",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary",
              "active:scale-[0.97]",
              enabled
                ? // 显示中：边框 = 指标色 + 浅背景高亮
                  "bg-bg-tertiary/60 border-[color:var(--indicator-color)]/60"
                : // 未显示：暗灰边框 + 弱化指标色
                  "bg-bg-secondary/60 border-[rgba(255,240,220,0.10)] hover:border-[rgba(255,240,220,0.20)]",
            )}
            style={{ ["--indicator-color" as any]: row.swatch }}
          >
            {/* 色块：solid 用纯色方块，dashed 用上下分割方块模拟虚线 */}
            <span
              data-testid={`indicator-swatch-${row.id}`}
              className="shrink-0 rounded"
              style={{
                width: "20px",
                height: "10px",
                background: swatchBg,
                boxShadow: swatchShadow,
                opacity: enabled ? 1 : 0.45,
              }}
              aria-hidden="true"
            />
            <span
              data-testid={`indicator-row-${row.id}`}
              className={cn(
                "text-[11px] font-medium tabular-nums whitespace-nowrap",
                enabled ? "text-text-primary" : "text-text-tertiary",
              )}
            >
              {row.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
