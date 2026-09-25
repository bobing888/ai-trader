import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ErrorStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

/** Error/empty state with optional retry action. */
export function ErrorState({ icon, title, description, action, className }: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center px-6 py-16 rounded-2xl",
        "bg-bg-secondary border border-bear/20 border-dashed",
        className,
      )}
      role="alert"
    >
      <div className="w-14 h-14 rounded-2xl bg-bear/10 border border-bear/20 flex items-center justify-center text-bear mb-4">
        {icon ?? <AlertTriangle className="w-6 h-6" />}
      </div>
      <h3 className="text-base font-semibold text-text-primary mb-1">{title}</h3>
      {description && <p className="text-sm text-text-secondary max-w-sm">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
