import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { cn } from "@/lib/utils";

export interface StatCardProps {
  label: string;
  /** Static value (when numericValue not provided). */
  value?: ReactNode;
  /** If value is a number, pass it here to enable count-up animation. */
  numericValue?: number;
  /** Format the animated number. */
  format?: (v: number) => string;
  change?: number;
  changeLabel?: string;
  icon?: ReactNode;
  tone?: "bull" | "bear" | "neutral";
}

export function StatCard({ label, value, numericValue, format, change, changeLabel, icon, tone = "neutral" }: StatCardProps) {
  const TrendIcon = change === undefined ? Minus : change > 0 ? ArrowUpRight : change < 0 ? ArrowDownRight : Minus;
  const trendColor =
    change === undefined
      ? "text-text-tertiary"
      : change > 0
        ? "text-bull"
        : change < 0
          ? "text-bear"
          : "text-text-tertiary";

  const valueColor = tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-text-primary";

  return (
    <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-4 flex flex-col gap-2 hover:border-[rgba(255,240,220,0.12)] transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-tertiary font-medium tracking-wide uppercase">{label}</span>
        {icon && <span className="text-text-tertiary">{icon}</span>}
      </div>
      <div className={cn("text-2xl font-semibold tabular-nums tracking-tight", valueColor)}>
        {numericValue !== undefined ? (
          <AnimatedNumber value={numericValue} format={format} />
        ) : (
          value
        )}
      </div>
      {(change !== undefined || changeLabel) && (
        <div className={cn("flex items-center gap-1 text-xs font-medium", trendColor)}>
          <TrendIcon className="w-3 h-3" />
          {change !== undefined && (
            <span className="tabular-nums">
              {change > 0 ? "+" : ""}
              {change.toFixed(2)}%
            </span>
          )}
          {changeLabel && <span className="text-text-tertiary">{changeLabel}</span>}
        </div>
      )}
    </div>
  );
}
