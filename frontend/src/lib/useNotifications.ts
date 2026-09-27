/**
 * useNotifications — polls the /api/notifications REST endpoint and surfaces
 * newly-arrived items via an optional `onNew` callback.
 *
 * The hook maintains an internal set of already-seen IDs so that only brand-new
 * notifications trigger the callback.  The returned `notifications` array
 * always reflects the latest fetched list (up to `limit` items, sorted
 * descending by `created_at`).
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface Notification {
  id: string;
  created_at: string;
  shift_type: "volatility_spike" | "volume_surge" | "trend_break" | "correlation_breakdown";
  severity: "low" | "medium" | "high";
  title: string;
  body: string;
  context: Record<string, unknown>;
  acknowledged: boolean;
}

export interface UseNotificationsReturn {
  notifications: Notification[];
  unseenCount: number;
  markSeen: (id: string) => void;
  ack: (id: string) => Promise<void>;
}

export interface UseNotificationsOptions {
  /** Polling interval in milliseconds (default 5000). */
  pollMs?: number;
  /** Number of most-recent notifications to request per poll (default 50). */
  limit?: number;
  /** Called once per newly-arrived notification. */
  onNew?: (notification: Notification) => void;
}

interface NotificationsResponse {
  items: Notification[];
}

async function fetchNotifications(limit: number): Promise<Notification[]> {
  const res = await fetch(`/api/notifications?limit=${limit}`);
  if (!res.ok) throw new Error(`fetch /api/notifications failed: ${res.status}`);
  const data = (await res.json()) as NotificationsResponse;
  return data.items;
}

async function postAck(id: string): Promise<void> {
  const res = await fetch(`/api/notifications/${id}/ack`, { method: "POST" });
  if (!res.ok) throw new Error(`ack failed: ${res.status}`);
}

export function useNotifications(options: UseNotificationsOptions = {}): UseNotificationsReturn {
  const { pollMs = 5000, limit = 50, onNew } = options;

  const [notifications, setNotifications] = useState<Notification[]>([]);

  /** Guards against stale-poll callbacks after unmount. */
  const aliveRef = useRef(true);

  /** Tracks seen IDs to diff against each fresh poll. */
  const seenIdsRef = useRef<Set<string>>(new Set());

  /**
   * Tracks in-flight poll epochs so we ignore responses from earlier runs.
   * Initialised to 1 so that after React 18 StrictMode's double-invocation
   * (mount → cleanup increments to 2 → remount increments to 3), the only
   * epoch still "active" when an async fetch resolves is 3 — preventing
   * stale responses from the first mount from firing onNew twice.
   */
  const pollEpochRef = useRef(1);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const poll = useCallback(async () => {
    const epoch = ++pollEpochRef.current;

    let items: Notification[];
    try {
      items = await fetchNotifications(limit);
    } catch (err) {
      console.warn("[useNotifications] poll failed:", err);
      return;
    }

    if (!aliveRef.current || epoch !== pollEpochRef.current) return;

    // Diff: find items with IDs we've never seen in this session.
    const newItems: Notification[] = [];
    for (const item of items) {
      if (!seenIdsRef.current.has(item.id)) {
        seenIdsRef.current.add(item.id);
        newItems.push(item);
      }
    }

    // Fire onNew outside the state setter to avoid stale-closure issues.
    for (const item of newItems) {
      onNew?.(item);
    }

    setNotifications(items);
  }, [limit, onNew]);

  // Start polling
  useEffect(() => {
    poll(); // immediate first fetch
    const id = setInterval(poll, pollMs);
    return () => clearInterval(id);
  }, [poll, pollMs]);

  const unseenCount = notifications.filter((n) => !n.acknowledged).length;

  const markSeen = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, acknowledged: true } : n)),
    );
  }, []);

  const ack = useCallback(async (id: string) => {
    await postAck(id);
    markSeen(id);
  }, [markSeen]);

  return { notifications, unseenCount, markSeen, ack };
}
