/**
 * useSignalStream — vitest unit tests.
 */
/// <reference types="vitest/globals" />

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("useSignalStream", () => {
  let wsInstances: MockWebSocket[];

  class MockWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;
    url: string;
    onopen: (() => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    readyState = MockWebSocket.CONNECTING;

    constructor(url: string) {
      this.url = url;
      wsInstances.push(this);
    }
    send = vi.fn();
    close() {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.();
    }
    // test helpers
    _simulateOpen() {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.();
    }
    _simulateMessage(data: unknown) {
      this.onmessage?.({ data: JSON.stringify(data) });
    }
    _simulateClose() {
      this.readyState = MockWebSocket.CLOSED;
      this.onclose?.();
    }
  }

  beforeEach(() => {
    wsInstances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.stubGlobal("location", {
      protocol: "http:",
      host: "localhost:5173",
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  // ── test_constructs_ws_to_correct_path ────────────────────────────────────
  it("constructs a WS to /api/recommendations/ws on mount", async () => {
    const { useSignalStream } = await import("@/lib/useSignalStream");
    renderHook(() => useSignalStream());
    expect(wsInstances).toHaveLength(1);
    expect(wsInstances[0]?.url).toBe("ws://localhost:5173/api/recommendations/ws");
  });

  // ── test_marks_connected_on_open ──────────────────────────────────────────
  it("isConnected becomes true after onopen", async () => {
    const { useSignalStream } = await import("@/lib/useSignalStream");
    const { result } = renderHook(() => useSignalStream());

    expect(result.current.isConnected).toBe(false);
    act(() => {
      wsInstances[0]?._simulateOpen();
    });
    expect(result.current.isConnected).toBe(true);
  });

  // ── test_parses_signal_change_message ──────────────────────────────────────
  it("updates lastEvent on signal_change message", async () => {
    const { useSignalStream } = await import("@/lib/useSignalStream");
    const { result } = renderHook(() => useSignalStream());

    act(() => {
      wsInstances[0]?._simulateOpen();
    });

    act(() => {
      wsInstances[0]?._simulateMessage({
        type: "signal_change",
        pair: "BTC-USDT",
        timeframe: "1h",
        change_type: "direction",
        current_id: 42,
        scanned_at: "2026-10-02T00:00:00Z",
      });
    });

    expect(result.current.lastEvent).toEqual({
      type: "signal_change",
      pair: "BTC-USDT",
      timeframe: "1h",
      change_type: "direction",
      current_id: 42,
      scanned_at: "2026-10-02T00:00:00Z",
    });
  });

  // ── test_ignores_non_signal_change ────────────────────────────────────────
  it("ignores non-signal_change messages", async () => {
    const { useSignalStream } = await import("@/lib/useSignalStream");
    const { result } = renderHook(() => useSignalStream());

    act(() => {
      wsInstances[0]?._simulateOpen();
    });

    act(() => {
      wsInstances[0]?._simulateMessage({ type: "ping" });
    });

    expect(result.current.lastEvent).toBeNull();
  });

  // ── test_reconnects_with_backoff_on_close ─────────────────────────────────
  it("schedules a reconnect on close (max 5 attempts)", async () => {
    vi.useFakeTimers();
    const { useSignalStream } = await import("@/lib/useSignalStream");
    renderHook(() => useSignalStream({ maxRetries: 3 }));

    act(() => {
      wsInstances[0]?._simulateOpen();
    });

    act(() => {
      wsInstances[0]?._simulateClose();
    });

    expect(wsInstances).toHaveLength(1);

    // First retry: ~1000ms backoff
    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(wsInstances.length).toBeGreaterThanOrEqual(2);
  });

  // ── test_no_reconnect_after_max_retries ───────────────────────────────────
  it("stops reconnecting after maxRetries exhausted", async () => {
    vi.useFakeTimers();
    const { useSignalStream } = await import("@/lib/useSignalStream");
    renderHook(() => useSignalStream({ maxRetries: 2 }));

    // Simulate 1 open + 1 close → retry 1
    act(() => {
      wsInstances[0]?._simulateOpen();
    });
    act(() => {
      wsInstances[0]?._simulateClose();
    });
    await act(async () => { vi.advanceTimersByTime(1100); });
    // retry 2nd
    act(() => {
      wsInstances[1]?._simulateClose();
    });
    await act(async () => { vi.advanceTimersByTime(2100); });
    // retry 3rd
    act(() => {
      wsInstances[2]?._simulateClose();
    });
    await act(async () => { vi.advanceTimersByTime(4100); });

    // After 3 closes (max=2 retries), no more new connections
    expect(wsInstances.length).toBeLessThanOrEqual(3);
  });
});
