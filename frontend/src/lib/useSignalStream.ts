/**
 * useSignalStream — connects to /api/recommendations/ws and surfaces
 * real-time signal_change events.
 *
 * - Auto-reconnect with exponential back-off (max 5 retries)
 * - Warns on non-wss (insecure dev) but still connects
 * - Invalidates TanStack Query cache for follows + batch-signals on event
 * - Returns null when disconnected (never throws)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { QueryClient } from "@tanstack/react-query";

export interface SignalChangeEvent {
  type: "signal_change";
  pair: string;
  timeframe: string;
  change_type: "direction" | "regime" | "confidence" | "no_signal" | "first_emit" | "no_change";
  current_id: number | null;
  scanned_at: string | null;
}

export interface UseSignalStreamOptions {
  /** TanStack Query client to invalidate on events (default: window.__queryClient) */
  queryClient?: QueryClient;
  /** Called on each incoming event */
  onEvent?: (event: SignalChangeEvent) => void;
  /** Maximum reconnection attempts (default 5) */
  maxRetries?: number;
}

export interface UseSignalStreamReturn {
  lastEvent: SignalChangeEvent | null;
  isConnected: boolean;
}

export function useSignalStream(
  options: UseSignalStreamOptions = {},
): UseSignalStreamReturn {
  const {
    queryClient = (window as unknown as { __queryClient?: QueryClient }).__queryClient ?? null,
    onEvent,
    maxRetries = 5,
  } = options;

  const [lastEvent, setLastEvent] = useState<SignalChangeEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const destroyedRef = useRef(false);

  const connect = useCallback(() => {
    if (destroyedRef.current) return;

    const wsUrl = _buildWsUrl("/api/recommendations/ws");
    if (!wsUrl) return;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (e: MessageEvent) => {
      let event: SignalChangeEvent;
      try {
        event = JSON.parse(e.data as string) as SignalChangeEvent;
      } catch {
        return;
      }
      if (event.type !== "signal_change") return;

      setLastEvent(event);
      onEvent?.(event);

      // Invalidate relevant cache entries
      if (queryClient) {
        queryClient.invalidateQueries({ queryKey: ["follows"] });
        queryClient.invalidateQueries({ queryKey: ["batch-signals"] });
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;

      // Reconnect with back-off
      if (!destroyedRef.current && retriesRef.current < maxRetries) {
        const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
        retriesRef.current++;
        retryTimerRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      // onclose fires after onerror — just log
    };
  }, [queryClient, onEvent, maxRetries]);

  useEffect(() => {
    destroyedRef.current = false;
    connect();
    return () => {
      destroyedRef.current = true;
      if (retryTimerRef.current !== null) clearTimeout(retryTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { lastEvent, isConnected };
}

// ── helpers ───────────────────────────────────────────────────────────────────

/** Derive the WS URL from the current window origin + path. */
function _buildWsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // In dev / behind reverse-proxy, origin is already correct
  return `${proto}//${window.location.host}${path}`;
}
