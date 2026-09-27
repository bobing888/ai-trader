/**
 * useRealtimeKlines — React hook that manages a WebSocket connection to the
 * backend K-line bridge and returns the merged candle array.
 *
 * Protocol:
 *   C→S: {"action": "set_channel", "channel": "candle1m"}
 *   S→C: {"type": "snapshot", "candles": [...]}   // 200 historical bars
 *   S→C: {"type": "update", "candle": {...}}     // real-time push
 *   S→C: {"type": "error", "detail": "..."}
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type Channel = "candle1m" | "candle5m" | "candle15m" | "candle1H" | "candle4H" | "candle1D";

export interface Kline {
  time: number;   // Unix second (lightweight-charts convention)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "down";

export interface UseRealtimeKlinesResult {
  candles: Kline[];
  status: ConnectionStatus;
  lastUpdate: Date | null;
}

// Server payload shapes
interface SnapshotMsg {
  type: "snapshot";
  candles: Kline[];
}

interface UpdateMsg {
  type: "update";
  candle: {
    ts: number;    // microseconds from OKX
    o: string | number;
    h: string | number;
    l: string | number;
    c: string | number;
    vol: string | number;
    confirm: boolean;
  };
}

interface ErrorMsg {
  type: "error";
  detail: string;
}

type ServerMsg = SnapshotMsg | UpdateMsg | ErrorMsg;

const MAX_RECONNECT_DELAY_MS = 30_000;
const BASE_RECONNECT_DELAY_MS = 1_000;

function useWebsocketScheme(): "ws" | "wss" {
  if (typeof window === "undefined") return "ws";
  return window.location.protocol === "https:" ? "wss" : "ws";
}

function parseCandle(raw: UpdateMsg["candle"]): Kline {
  return {
    time: Math.floor(raw.ts / 1_000_000),
    open: Number(raw.o),
    high: Number(raw.h),
    low: Number(raw.l),
    close: Number(raw.c),
    volume: Number(raw.vol),
  };
}

export function useRealtimeKlines(inst: string, channel: Channel): UseRealtimeKlinesResult {
  const [candles, setCandles] = useState<Kline[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  // Refs to avoid stale closures in the reconnect loop
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(BASE_RECONNECT_DELAY_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const instRef = useRef(inst);
  const channelRef = useRef(channel);
  // True while the component wants the connection alive
  const reconnectActiveRef = useRef(true);

  // Keep refs in sync
  useEffect(() => {
    instRef.current = inst;
    channelRef.current = channel;
  }, [inst, channel]);

  const connect = useCallback(() => {
    // Tear down existing connection
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    setStatus("connecting");
    const scheme = useWebsocketScheme();
    const host = typeof window !== "undefined" ? window.location.host : "localhost:8000";
    const url = `${scheme}://${host}/api/ws/klines/${instRef.current}?channel=${channelRef.current}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      reconnectDelayRef.current = BASE_RECONNECT_DELAY_MS;
      // Tell the server which channel we want
      ws.send(JSON.stringify({ action: "set_channel", channel: channelRef.current }));
    };

    ws.onmessage = (event: MessageEvent) => {
      let msg: ServerMsg;
      try {
        msg = JSON.parse(event.data as string) as ServerMsg;
      } catch {
        return;
      }

      if (msg.type === "snapshot") {
        const sorted = [...msg.candles].sort((a, b) => a.time - b.time);
        setCandles(sorted);
        setLastUpdate(new Date());
      } else if (msg.type === "update") {
        const kline = parseCandle(msg.candle);
        setCandles((prev) => {
          const idx = prev.findIndex((c) => c.time === kline.time);
          if (idx >= 0) {
            // Update in place (last candle may change)
            const next = [...prev];
            next[idx] = kline;
            return next;
          }
          // Append and keep sorted
          return [...prev, kline].sort((a, b) => a.time - b.time);
        });
        setLastUpdate(new Date());
      } else if (msg.type === "error") {
        console.warn("[useRealtimeKlines] server error:", msg.detail);
      }
    };

    ws.onerror = () => {
      // onerror is always followed by onclose; handle reconnect there
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (reconnectActiveRef.current) {
        scheduleReconnect();
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }
    setStatus("reconnecting");
    const delay = reconnectDelayRef.current;
    reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);
    reconnectTimerRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]); // eslint-disable-line react-hooks/exhaustive-deps

  // Start the connection on mount / when inst or channel changes
  useEffect(() => {
    reconnectActiveRef.current = true;
    connect();
    return () => {
      reconnectActiveRef.current = false;
      setStatus("down");
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inst, channel]);

  return { candles, status, lastUpdate };
}
