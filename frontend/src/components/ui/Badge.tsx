import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone = "default" | "accent" | "bull" | "bear" | "warning" | "info" | "muted";

export interface BadgeProps {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  className?: string;
}

const toneClasses: Record<Tone, string> = {
  default: "bg-bg-tertiary text-text-secondary border border-[rgba(255,240,220,0.06)]",
  accent: "bg-accent/10 text-accent border border-accent/20",
  bull: "bg-bull/10 text-bull border border-bull/20",
  bear: "bg-bear/10 text-bear border border-bear/20",
  warning: "bg-warning/10 text-warning border border-warning/20",
  info: "bg-info/10 text-info border border-info/20",
  muted: "bg-transparent text-text-tertiary border border-[rgba(255,240,220,0.08)]",
};

export function Badge({ children, tone = "default", icon, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full text-[11px] font-medium tracking-wide",
        toneClasses[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
