/**
 * NotificationProvider — React context + hook for notification state + toast queue.
 *
 * Lives at the root of the app (inside BrowserRouter) and owns:
 *   1. the `useNotifications` polling hook
 *   2. the in-memory toast queue (capped at 3 visible toasts)
 *   3. a `useNotification` consumer hook
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
