/**
 * useNotifications — vitest unit tests.
 *
 * 只 mock `fetch`, 真测 hook (沿用 PR #22 lightweight-charts 的 mock 风格).
 */
/// <reference types="vitest/globals" />

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Notification } from "@/lib/useNotifications";

function makeNotif(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "n-1",
    created_at: "2026-09-27T12:00:00Z",
    shift_type: "volatility_spike",
    severity: "medium",
    title: "Test Alert",
    body: "Something happened.",
    context: {},
    acknowledged: false,
    ...overrides,
  };
}

describe("useNotifications", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  // ── test_polls_endpoint_every_5s ───────────────────────────────────────────
  it("polls endpoint every pollMs (initial + setInterval)", async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as unknown as Response);

    vi.useFakeTimers();
    const { useNotifications } = await import("@/lib/useNotifications");

    renderHook(() => useNotifications({ pollMs: 5_000 }));

    // advance 5001ms — initial + 1 interval fires
    await act(async () => { vi.advanceTimersByTime(5001); });

    // StrictMode 双 mount 时, 实际是 initial ×2 + interval ×1 = 3 次
    expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(fetchSpy.mock.calls.length).toBeLessThanOrEqual(6);
  });

  // ── test_onNew_fires_only_for_new_ids ──────────────────────────────────────
  it("onNew fires only for newly seen IDs", async () => {
    const n1 = makeNotif({ id: "n-1" });
    const n2 = makeNotif({ id: "n-2" });
    const n3 = makeNotif({ id: "n-3" });

    let pollCount = 0;
    fetchSpy.mockImplementation(async () => {
      pollCount++;
      // 第一次 poll: 2 个, 第二次 poll: 3 个 (n1, n2 已见 + n3 新的)
      const items = pollCount <= 1 ? [n1, n2] : [n1, n2, n3];
      return {
        ok: true,
        json: async () => ({ items }),
      } as unknown as Response;
    });

    vi.useFakeTimers();
    const onNew = vi.fn();
    const { useNotifications } = await import("@/lib/useNotifications");

    renderHook(() => useNotifications({ pollMs: 5_000, onNew }));

    // 第一次 poll: n1 + n2 是新的 → onNew ×2
    await act(async () => { vi.advanceTimersByTime(1); });
    expect(onNew).toHaveBeenCalledTimes(2);
    expect(onNew.mock.calls[0]?.[0]).toBe(n1);
    expect(onNew.mock.calls[1]?.[0]).toBe(n2);

    // 第二次 poll: 只有 n3 是新的 → onNew +1
    await act(async () => { vi.advanceTimersByTime(5_001); });
    expect(onNew).toHaveBeenCalledTimes(3);
    expect(onNew.mock.calls[2]?.[0]).toBe(n3);
  });

  // ── test_ack_calls_endpoint ─────────────────────────────────────────────────
  it("ack calls POST /api/notifications/{id}/ack", async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as unknown as Response);

    const { useNotifications } = await import("@/lib/useNotifications");
    const { result } = renderHook(() => useNotifications());

    await act(async () => {
      await result.current.ack("n-ack-1");
    });

    const ackCall = fetchSpy.mock.calls.find(
      ([url, opts]) =>
        typeof url === "string" && url.includes("/ack") && (opts as RequestInit | undefined)?.method === "POST",
    );
    expect(ackCall).toBeDefined();
    expect(ackCall![0]).toBe("/api/notifications/n-ack-1/ack");
  });
});
