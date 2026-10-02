/**
 * NotificationProvider — React context + hook for notification state + toast queue.
 *
 * Lives at the root of the app (inside BrowserRouter) and owns:
 *   1. the `useNotifications` polling hook
 *   2. the in-memory toast queue (capped at 3 visible toasts)
 *   3. a `useNotification` consumer hook
 *   4. D5: `useSignalAudio` — WebSocket signal alerts → Web Audio + browser notification
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";

import { useNotifications, type Notification } from "@/lib/useNotifications";
import { NotificationToaster } from "./NotificationToaster";
import { useSignalStream, type SignalAlert } from "@/lib/useSignalStream";
import {
  playSignalAlert,
  sendBrowserNotification,
  formatSignalNotification,
} from "@/lib/audio";

// ── context value ─────────────────────────────────────────────────────────────

export interface NotificationContextValue {
  notifications: Notification[];
  toasts: Notification[];
  unseenCount: number;
  markSeen: (id: string) => void;
  ack: (id: string) => Promise<void>;
}

const NotificationContext = createContext<NotificationContextValue | null>(null);

export function useNotificationContext(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotificationContext must be used inside <NotificationProvider>");
  return ctx;
}

// ── D5: signal audio hook ────────────────────────────────────────────────────

function useSignalAudio(): void {
  const cooldowns = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useSignalStream({
    onAlert: (alert: SignalAlert) => {
      // 30s cooldown per pair
      if (cooldowns.current[alert.pair]) return;
      cooldowns.current[alert.pair] = setTimeout(() => {
        delete cooldowns.current[alert.pair];
      }, 30_000);

      // D5: Web Audio tone (only high/medium reach here)
      playSignalAlert(alert.quality as "high" | "medium");

      // D5: browser notification (quality is "high" | "medium" after filter)
      const payload = formatSignalNotification({
        pair: alert.pair,
        direction: alert.direction,
        quality: alert.quality as "high" | "medium",
        entry_levels: alert.entry_levels,
        stop_loss_price: alert.stop_loss_price,
        take_profit_1_price: alert.take_profit_1_price,
        atr: alert.atr,
      });
      sendBrowserNotification(payload);
    },
  });
}

// ── provider ──────────────────────────────────────────────────────────────────

const MAX_VISIBLE_TOASTS = 3;

export function NotificationProvider({ children }: PropsWithChildren): JSX.Element {
  const [toasts, setToasts] = useState<Notification[]>([]);

  const onNew = useCallback((notification: Notification) => {
    setToasts((prev) => {
      const next = [...prev, notification];
      return next.length > MAX_VISIBLE_TOASTS ? next.slice(-MAX_VISIBLE_TOASTS) : next;
    });

    const ttlMs = notification.severity === "high" ? 8000 : 4000;
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== notification.id));
    }, ttlMs);
  }, []);

  const { notifications, unseenCount, markSeen, ack } = useNotifications({ onNew });

  // D5: WebSocket signal audio + browser notification (always-on at root)
  useSignalAudio();

  const initializedRef = useRef(false);
  useEffect(() => {
    initializedRef.current = true;
  }, []);

  return (
    <NotificationContext.Provider value={{ notifications, toasts, unseenCount, markSeen, ack }}>
      {children}
      <NotificationToaster />
    </NotificationContext.Provider>
  );
}
