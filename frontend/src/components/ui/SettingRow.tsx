import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SettingRowProps {
  icon?: ReactNode;
  iconTone?: "default" | "accent" | "info" | "warning" | "bull" | "bear";
  title: string;
  description?: string;
  /** Control element rendered on the right (toggle, select, button, etc). */
  control?: ReactNode;
  /** Optional trailing metadata text (e.g. "v0.1.0"). */
  meta?: ReactNode;
  /** Hide divider below this row. */
  noDivider?: boolean;
  className?: string;
}

const TONE_CLASS = {
  default: "bg-bg-tertiary text-text-tertiary border-[rgba(255,240,220,0.06)]",
  accent: "bg-accent/15 text-accent border-accent/25",
  info: "bg-info/15 text-info border-info/25",
  warning: "bg-warning/15 text-warning border-warning/25",
  bull: "bg-bull/15 text-bull border-bull/25",
  bear: "bg-bear/15 text-bear border-bear/25",
};

export function SettingRow({
  icon,
  iconTone = "default",
  title,
  description,
  control,
  meta,
  noDivider,
  className,
}: SettingRowProps) {
  return (
    <div className={cn(!noDivider && "border-b border-[rgba(255,240,220,0.04)]", className)}>
      <div className="flex items-center gap-4 py-3.5 px-1">
        {icon && (
          <div
            className={cn(
              "shrink-0 w-9 h-9 rounded-xl flex items-center justify-center border",
              TONE_CLASS[iconTone],
            )}
          >
            {icon}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-text-primary">{title}</div>
          {description && (
            <div className="text-xs text-text-tertiary mt-0.5 leading-relaxed">{description}</div>
          )}
        </div>
        {meta && <div className="text-xs text-text-tertiary mr-2">{meta}</div>}
        {control && <div className="shrink-0">{control}</div>}
      </div>
    </div>
  );
}
