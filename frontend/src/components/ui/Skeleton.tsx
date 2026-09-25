import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  /** Pre-built rounded shape variants. */
  variant?: "text" | "circular" | "rectangular" | "pill";
  /** Width — accepts tailwind class or arbitrary value. */
  width?: string;
  /** Height — accepts tailwind class or arbitrary value. */
  height?: string;
}

const variantClass = {
  text: "rounded",
  circular: "rounded-full",
  rectangular: "rounded-xl",
  pill: "rounded-full",
};

/** Shimmer placeholder for loading content. Uses .animate-shimmer from index.css. */
export function Skeleton({
  className,
  variant = "text",
  width,
  height,
  style,
  ...rest
}: SkeletonProps) {
  return (
    <div
      className={cn(
        "bg-bg-tertiary relative overflow-hidden",
        variantClass[variant],
        className,
      )}
      style={{ width, height, ...style }}
      aria-busy="true"
      aria-live="polite"
      {...rest}
    >
      <div className="absolute inset-0 animate-shimmer" />
    </div>
  );
}

/** Pre-built layouts for common UI patterns. */

export function SkeletonStatCard() {
  return (
    <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <Skeleton variant="text" width="64px" height="10px" />
        <Skeleton variant="circular" width="14px" height="14px" />
      </div>
      <Skeleton variant="text" width="80%" height="24px" />
      <Skeleton variant="text" width="50%" height="10px" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden">
      <div className="grid grid-cols-7 gap-4 px-5 py-3 border-b border-[rgba(255,240,220,0.06)]">
        {Array.from({ length: 7 }).map((_, i) => (
          <Skeleton key={i} variant="text" width="60%" height="10px" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="grid grid-cols-7 gap-4 px-5 py-4 border-b border-[rgba(255,240,220,0.04)]">
          {Array.from({ length: 7 }).map((_, j) => (
            <Skeleton key={j} variant="text" width={`${50 + ((i + j) % 5) * 10}%`} height="12px" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-5 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Skeleton variant="circular" width="32px" height="32px" />
        <Skeleton variant="text" width="40%" height="14px" />
      </div>
      <Skeleton variant="text" width="100%" height="12px" />
      <Skeleton variant="text" width="80%" height="12px" />
      <div className="flex gap-2 pt-2">
        <Skeleton variant="pill" width="60px" height="20px" />
        <Skeleton variant="pill" width="80px" height="20px" />
      </div>
    </div>
  );
}
