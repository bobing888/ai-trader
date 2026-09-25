import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  width?: "sm" | "md" | "lg";
}

const widthClasses: Record<NonNullable<DrawerProps["width"]>, string> = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-2xl",
};

export function Drawer({ open, onClose, title, children, width = "md" }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-[fade-in_0.2s_ease-out]"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={cn(
          "relative ml-auto h-full w-full bg-bg-primary border-l border-[rgba(255,240,220,0.06)]",
          "shadow-[-24px_0_48px_-12px_rgba(0,0,0,0.6)] flex flex-col",
          widthClasses[width],
          "animate-[slide-in-right_0.3s_cubic-bezier(0.16,1,0.3,1)]",
        )}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-[rgba(255,240,220,0.06)]">
          <h2 className="text-base font-semibold text-text-primary">{title}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>
  );
}
