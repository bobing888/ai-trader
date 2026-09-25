import { Toggle } from "@/components/ui/Toggle";
import type { ChartPreferences } from "@/lib/preferences";

// 用户重点关注：MA 系列（5/10/20/30/60）+ BOLL（布林带）
// 配色方案：MA 暖色系（短周期浅色，长周期深色），BOLL 冷色系（青/蓝），与黑色背景高对比
export const MA_BOLL_COLORS = {
  ma5:  "#fef3c7", // warm white — 极短周期，紧贴价
  ma10: "#fbbf24", // amber
  ma20: "#fb923c", // orange
  ma30: "#f43f5e", // rose
  ma60: "#a855f7", // violet
  bollUpper: "rgba(96, 165, 250, 0.85)",  // sky blue 虚线
  bollMid:   "#22d3ee",                    // cyan 实线
  bollLower: "rgba(96, 165, 250, 0.85)",
} as const;

interface ToggleRow {
  id: string;
  label: string;
  swatch: string;
  /** "solid" | "dashed" — 仅视觉描述 */
  style?: "solid" | "dashed";
  hint?: string;
}

const ROWS: ToggleRow[] = [
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
 * K 线指标开关面板 — 用户重点关注 MA 系列（5/10/20/30/60）+ BOLL（布林带）。
 * 每个 MA 独立 toggle；BOLL 一个 toggle 同时控制 3 条线（中轨 + 上下轨）。
 * 渲染：色块 + 指标名 + 简短说明 + Toggle 开关。
 * 数据流：组件是纯展示，切换触发 onChange(id, enabled)；
 * 父组件（KlinePage）负责写 prefs 并 reload KlineChart。
 */
export function IndicatorTogglePanel({ prefs, onChange }: IndicatorTogglePanelProps) {
  return (
    <div className="flex flex-col gap-1" data-testid="indicator-toggle-panel">
      <div className="px-1 pb-2 text-[10px] uppercase tracking-wider text-text-tertiary">
        主图指标 (MA · BOLL)
      </div>
      {ROWS.map((row) => {
        const enabled = !!prefs.indicators[row.id]?.enabled;
        return (
          <div
            key={row.id}
            data-testid={`indicator-row-${row.id}`}
            className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-bg-tertiary/40 transition-colors"
          >
            {/* 色块：solid 用纯色方块，dashed 用上下分割方块模拟虚线 */}
            <span
              data-testid={`indicator-swatch-${row.id}`}
              className="shrink-0 rounded"
              style={{
                width: "22px",
                height: "10px",
                background: row.style === "dashed"
                  ? `linear-gradient(to bottom, ${row.swatch} 0 3px, transparent 3px 7px, ${row.swatch} 7px 10px)`
                  : row.swatch,
                boxShadow: row.style === "dashed" ? "none" : `0 0 6px ${row.swatch}40`,
              }}
              aria-hidden="true"
            />
            <div className="flex-1 min-w-0">
              <div className="text-[12px] font-medium text-text-primary leading-tight">
                {row.label}
              </div>
              {row.hint && (
                <div className="text-[10px] text-text-tertiary leading-tight mt-0.5">
                  {row.hint}
                </div>
              )}
            </div>
            <Toggle
              checked={enabled}
              size="sm"
              label={`Toggle ${row.label}`}
              onChange={(next) => onChange(row.id, next)}
              data-testid={`indicator-toggle-${row.id}`}
            />
          </div>
        );
      })}
    </div>
  );
}
