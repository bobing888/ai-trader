/**
 * useSignalStream — connects to /api/recommendations/ws and surfaces
 * real-time signal_change events.
 *
 * D4 upgrade: full payload with entry_levels, SL, TP, quality, current_price.
 * - Auto-reconnect with exponential back-off (max 5 retries)
 * - Warns on non-wss (insecure dev) but still connects
 * - Invalidates TanStack Query cache for follows + batch-signals on event
 * - Returns null when disconnected (never throws)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { QueryClient } from "@tanstack/react-query";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface EntryLevel {
  price: number;
  size_pct: number;
  label: string;
}

export interface SignalPayload {
  id: number;
  pair: string;
  timeframe: string;
  has_signal: boolean;
  direction: "long" | "short" | null;
  confidence: number | null;
  regime: string | null;
  regime_confidence: number | null;
  contributing_strategies: string[];
  reasons: string[];
  suggested_leverage: number | null;
  min_agreement_used: number | null;
  fast_path: boolean;
  outcome: string;
  scanned_at: string | null;
  source: string;
  // Phase 1
  calibrated_confidence: number | null;
  net_pnl_estimate: number | null;
  // D1
  entry_levels: EntryLevel[];
  stop_loss_price: number | null;
  take_profit_1_price: number | null;
  take_profit_2_price: number | null;
  atr: number | null;
  risk_reward_ratio: number | null;
  current_price: number | null;
  // D2
  quality: "high" | "medium" | "low" | "reject" | null;
  quality_reasons: string[];
}

export interface SignalChangeEvent {
  type: "signal_change";
  change_type: "direction" | "regime" | "confidence" | "no_signal" | "first_emit" | "no_change" | "initial_snapshot";
  pair: string;
  timeframe: string;
  current: SignalPayload | null;
  previous: SignalPayload | null;
}

// D5: notification event emitted by hook to consumer components
export interface SignalAlert {
  pair: string;
  direction: "long" | "short";
  quality: "high" | "medium" | "low" | null;
  change_type: string;
  entry_levels: EntryLevel[];
  stop_loss_price: number | null;
  take_profit_1_price: number | null;
  atr: number | null;
}

// ─── Options ─────────────────────────────────────────────────────────────────

export interface UseSignalStreamOptions {
  /** TanStack Query client to invalidate on events (default: window.__queryClient) */
  queryClient?: QueryClient;
  /** Called on each incoming event */
  onEvent?: (event: SignalChangeEvent) => void;
  /** Called on high/medium quality signal changes (for D5 audio alerts) */
  onAlert?: (alert: SignalAlert) => void;
  /** Maximum reconnection attempts (default 5) */
  maxRetries?: number;
}

export interface UseSignalStreamReturn {
  lastEvent: SignalChangeEvent | null;
  isConnected: boolean;
}

// ─── Hook ────────────────────────────────────────────────────────────────────

export function useSignalStream(
  options: UseSignalStreamOptions = {},
): UseSignalStreamReturn {
  const {
    queryClient = (window as unknown as { __queryClient?: QueryClient }).__queryClient ?? null,
    onEvent,
    onAlert,
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

      // D5: trigger audio/notification for quality signals
      if (
        onAlert &&
        event.current &&
        event.current.has_signal &&
        (event.current.quality === "high" || event.current.quality === "medium")
      ) {
        onAlert({
          pair: event.current.pair,
          direction: event.current.direction as "long" | "short",
          quality: event.current.quality as "high" | "medium",
          change_type: event.change_type,
          entry_levels: event.current.entry_levels ?? [],
          stop_loss_price: event.current.stop_loss_price ?? null,
          take_profit_1_price: event.current.take_profit_1_price ?? null,
          atr: event.current.atr ?? null,
        });
      }

      setLastEvent(event);
      onEvent?.(event);

      // Invalidate relevant cache entries
      if (queryClient) {
        queryClient.invalidateQueries({ queryKey: ["follows"] });
        queryClient.invalidateQueries({ queryKey: ["batch-signals"] });
        queryClient.invalidateQueries({ queryKey: ["recommendation-history"] });
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
  }, [queryClient, onEvent, onAlert, maxRetries]);

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

// ─── helpers ─────────────────────────────────────────────────────────────────

/** Derive the WS URL from the current window origin + path. */
function _buildWsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  // In dev / behind reverse-proxy, origin is already correct
  return `${proto}//${window.location.host}${path}`;
}
