import { useEffect, useState } from "react";
import type { IndicatorPref } from "@/lib/preferences";
import { cn } from "@/lib/utils";

export interface IndicatorParamsModalProps {
  /** null = modal 关闭 */
  indicatorId: string | null;
  /** 指标显示名（顶部标题用） */
  label: string;
  /** 当前 prefs — 提供当前 params 给用户改 */
  pref: IndicatorPref | undefined;
  /** 默认参数（用于"重置"按钮） */
  defaultParams: Record<string, number | string | boolean>;
  /** 用户点保存 */
  onSave: (indicatorId: string, params: Record<string, number | string | boolean>) => void;
  /** 关闭 modal */
  onClose: () => void;
}

/**
 * 指标参数编辑 modal — IndicatorTogglePanel 右键 / 双击 chip 时弹出。
 * 显示当前 params 的每个键作为输入框，用户改完点"保存"回写 prefs。
 * 不引入第三方 modal 库（规则 3：增量优化），用原生 dialog + tailwind 实现。
 */
export function IndicatorParamsModal({
  indicatorId,
  label,
  pref,
  defaultParams,
  onSave,
  onClose,
}: IndicatorParamsModalProps) {
  const [draft, setDraft] = useState<Record<string, string>>({});

  // 每次打开 modal 时，用当前 pref 初始化草稿
  useEffect(() => {
    if (!indicatorId || !pref) return;
    const init: Record<string, string> = {};
    for (const [k, v] of Object.entries(pref.params)) {
      init[k] = String(v);
    }
    setDraft(init);
  }, [indicatorId, pref]);

  if (!indicatorId) return null;

  const allKeys = Array.from(new Set([...Object.keys(defaultParams), ...Object.keys(draft)]));

  const handleChange = (key: string, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    const next: Record<string, number | string | boolean> = {};
    for (const k of allKeys) {
      const raw = draft[k];
      if (raw === undefined || raw === "") continue;
      const asNum = Number(raw);
      next[k] = Number.isFinite(asNum) && raw.trim() !== "" ? asNum : raw;
    }
    onSave(indicatorId, next);
    onClose();
  };

  const handleReset = () => {
    const init: Record<string, string> = {};
    for (const [k, v] of Object.entries(defaultParams)) {
      init[k] = String(v);
    }
    setDraft(init);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`编辑 ${label} 参数`}
      data-testid={`indicator-params-modal-${indicatorId}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          "w-[min(420px,90vw)] rounded-2xl bg-bg-secondary",
          "border border-[rgba(255,240,220,0.10)] shadow-2xl",
          "p-5 flex flex-col gap-4",
        )}
      >
        <header className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">
            {label} <span className="text-text-tertiary text-[11px] font-normal">参数</span>
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            data-testid={`indicator-params-close-${indicatorId}`}
            className="text-text-tertiary hover:text-text-primary text-xs px-2 py-1 rounded"
          >
            ✕
          </button>
        </header>

        <div className="flex flex-col gap-3">
          {allKeys.length === 0 && (
            <p className="text-xs text-text-tertiary">该指标无参数可调</p>
          )}
          {allKeys.map((key) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-[11px] text-text-tertiary font-medium">{key}</span>
              <input
                type="text"
                inputMode="decimal"
                value={draft[key] ?? ""}
                onChange={(e) => handleChange(key, e.target.value)}
                data-testid={`indicator-params-input-${indicatorId}-${key}`}
                className={cn(
                  "h-9 px-3 rounded-lg",
                  "bg-bg-tertiary text-text-primary text-sm tabular-nums",
                  "border border-[rgba(255,240,220,0.10)]",
                  "focus:outline-none focus:border-accent/60",
                )}
              />
            </label>
          ))}
        </div>

        <footer className="flex items-center justify-between mt-1">
          <button
            type="button"
            onClick={handleReset}
            data-testid={`indicator-params-reset-${indicatorId}`}
            className="text-[11px] text-text-tertiary hover:text-text-secondary underline-offset-2 hover:underline"
          >
            重置为默认
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              data-testid={`indicator-params-cancel-${indicatorId}`}
              className="h-8 px-3 text-xs text-text-secondary hover:text-text-primary rounded-lg"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSave}
              data-testid={`indicator-params-save-${indicatorId}`}
              className={cn(
                "h-8 px-4 text-xs font-medium rounded-lg",
                "bg-accent text-bg-primary hover:opacity-90",
                "active:scale-[0.97] transition-all",
              )}
            >
              保存
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
