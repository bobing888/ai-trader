/**
 * NotificationToast — a single notification toast card.
 *
 * Renders in the top-right corner with:
 *   - medium  → blue-grey background, 4s auto-dismiss
 *   - high   → red background, 8s auto-dismiss, animate-pulse
 *
 * The toast is fully controlled by props; auto-dismiss timer is owned by
 * NotificationProvider.
 */

import { X } from "lucide-react";

import type { Notification } from "@/lib/useNotifications";
import { cn } from "@/lib/utils";

interface NotificationToastProps {
  notification: Notification;
  onAck: (id: string) => void;
  onDismiss: (id: string) => void;
}

const SHIFT_ICONS: Record<Notification["shift_type"], string> = {
  volatility_spike: "V",
  volume_surge: "Vol",
  trend_break: "TB",
  correlation_breakdown: "Corr",
};

export function NotificationToast({ notification, onAck, onDismiss }: NotificationToastProps) {
  const isHigh = notification.severity === "high";

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "relative w-72 rounded-2xl px-4 py-3 shadow-2xl",
        "flex items-start gap-3 animate-slide-up",
        isHigh
          ? "bg-bear/90 text-white animate-pulse"
          : "bg-bg-secondary border border-[rgba(255,240,220,0.08)] text-text-primary",
      )}
    >
      {/* Badge */}
      <div
        className={cn(
          "shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold",
          isHigh
            ? "bg-white/20 text-white"
            : {
                "bg-blue-500/20 text-blue-400": notification.shift_type === "volume_surge",
                "bg-orange-500/20 text-orange-400":
                  notification.shift_type === "volatility_spike",
                "bg-red-500/20 text-red-400": notification.shift_type === "trend_break",
                "bg-purple-500/20 text-purple-400":
                  notification.shift_type === "correlation_breakdown",
              },
        )}
      >
        {SHIFT_ICONS[notification.shift_type]}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold leading-tight">{notification.title}</div>
        <div className="text-xs mt-0.5 leading-snug text-text-secondary">{notification.body}</div>
      </div>

      {/* Actions */}
      <div className="shrink-0 flex flex-col items-end gap-1.5">
        <button
          onClick={() => onDismiss(notification.id)}
          aria-label="Dismiss"
          className="p-0.5 rounded-full text-white/60 hover:text-white hover:bg-white/10 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onAck(notification.id)}
          className={cn(
            "text-xs px-2 py-0.5 rounded-full font-medium transition-colors cursor-pointer",
            isHigh
              ? "bg-white/20 text-white hover:bg-white/30"
              : "bg-accent/20 text-accent hover:bg-accent/30",
          )}
        >
          Ack
        </button>
      </div>
    </div>
  );
}
