import { cn } from "@/lib/utils";
import type { ChartPreferences } from "@/lib/preferences";
import type { IndicatorDef } from "./IndicatorTogglePanel.types";

interface IndicatorTogglePanelProps {
  prefs: ChartPreferences;
  /** 父组件传入要渲染的指标列表 — 通常是 KlineChart 的 OVERLAY_DEFS + PANEL_DEFS 的子集 */
  defs: IndicatorDef[];
  onChange: (indicatorId: string, enabled: boolean) => void;
  /** 长按 / 右键 / 双击 chip 调出参数编辑（父组件决定 UI：modal / inline / drawer） */
  onEditParams?: (indicatorId: string) => void;
}

/**
 * K 线指标管理面板 — 把"主图叠层"和"副图指标"合并到一个卡片内两个 section。
 * - Section 1：主图叠层（defs.filter(overlay === true)）
 * - Section 2：副图指标（defs.filter(overlay === false)）
 *
 * 每个 chip = 一个完整的可点击 button：
 *   - 左键单击 → 切换 on/off（onChange(id, !enabled)）
 *   - 双击 / 右键 → 调出参数编辑（onEditParams(id)，可选）
 *
 * 数据流：组件是纯展示，切换由父组件（KlinePage）写 prefs 并 reload KlineChart。
 *
 * 为什么本文件只 export function：
 * - Vite Fast Refresh 对 mixed export（interface + function）触发 full reload，
 *   KlineChart 在 prefs 重 mount 时撞 React StrictMode 双调用导致
 *   "Rendered more hooks than during the previous render" race。
 * - 把所有 types 移到 ./IndicatorTogglePanel.types.ts（type-only export，编译时擦除），
 *   本文件只剩 React component → Fast Refresh 走 hot module replacement，无 race。
 */
export function IndicatorTogglePanel({ prefs, defs, onChange, onEditParams }: IndicatorTogglePanelProps) {
  const overlayDefs = defs.filter((d) => d.overlay);
  const subpaneDefs = defs.filter((d) => !d.overlay);

  const renderChip = (row: IndicatorDef) => {
    const enabled = !!prefs.indicators[row.id]?.enabled;
    const isDashed = row.style === "dashed";
    const swatchBg = isDashed
      ? `linear-gradient(to bottom, ${row.color} 0 3px, transparent 3px 7px, ${row.color} 7px 10px)`
      : row.color;
    const swatchShadow = isDashed ? "none" : `0 0 6px ${row.color}55`;
    return (
      <button
        key={row.id}
        type="button"
        aria-pressed={enabled}
        aria-label={`${row.label}（${enabled ? "已显示" : "未显示"}，单击切换，右键或双击改参数）`}
        title={row.hint ?? `${row.label} — 单击切换，右键/双击改参数`}
        data-testid={`indicator-toggle-${row.id}`}
        onClick={() => onChange(row.id, !enabled)}
        onDoubleClick={(e) => {
          e.preventDefault();
          onEditParams?.(row.id);
        }}
        onContextMenu={(e) => {
          e.preventDefault();
          onEditParams?.(row.id);
        }}
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
        style={{ ["--indicator-color" as any]: row.color }}
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
  };

  return (
    <div
      className="flex flex-col gap-3"
      data-testid="indicator-toggle-panel"
      role="toolbar"
      aria-label="K 线指标切换"
    >
      {overlayDefs.length > 0 && (
        <div
          data-testid="indicator-section-overlay"
          className="flex flex-row flex-wrap items-center gap-2"
        >
          {overlayDefs.map(renderChip)}
        </div>
      )}
      {subpaneDefs.length > 0 && (
        <div
          data-testid="indicator-section-subpane"
          className="flex flex-row flex-wrap items-center gap-2"
        >
          {subpaneDefs.map(renderChip)}
        </div>
      )}
    </div>
  );
}
