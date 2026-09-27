/**
 * NotificationToaster — component tests.
 *
 * 通过 react-testing-library 的 `render()` 触发 NotificationProvider 挂载,
 * 它会用 mock 的 useNotifications. onNew 是 mock implementation **内手动触发**
 * (即 mock 自己调), 我们避免无限循环 — 因为 onNew 来自 useCallback([]),
 * 它引用恒定, 不会触发 setToasts 后导致 mock 重跑.
 */
/// <reference types="vitest/globals" />

import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Notification } from "@/lib/useNotifications";
import { useNotifications } from "@/lib/useNotifications";
import { NotificationProvider } from "@/components/notifications/NotificationProvider";
import { NotificationToaster } from "@/components/notifications/NotificationToaster";

vi.mock("@/lib/useNotifications", () => ({
  useNotifications: vi.fn(),
}));

const useNotificationsMock = vi.mocked(useNotifications);

function makeNotif(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "toast-1",
    created_at: "2026-09-27T12:00:00Z",
    shift_type: "volatility_spike",
    severity: "medium",
    title: "Volatility Spike Detected",
    body: "BTC-USDT volatility is 3x higher than 1h average.",
    context: {},
    acknowledged: false,
    ...overrides,
  };
}

describe("NotificationToaster", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;
  let pendingNewCb: ((n: Notification) => void) | null = null;

  beforeEach(() => {
    fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchSpy);
    pendingNewCb = null;

    // 默认 mock: 不自动触发 onNew, 由测试在 render 后手动 push 一条
    useNotificationsMock.mockImplementation(
      (opts?: { onNew?: (n: Notification) => void }) => {
        if (opts?.onNew) pendingNewCb = opts.onNew;
        return {
          notifications: [],
          unseenCount: 0,
          markSeen: vi.fn(),
          ack: vi.fn(async () => {}),
        };
      },
    );
  });

  afterEach(() => {
    useNotificationsMock.mockReset();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  function pushToast(n: Notification): void {
    expect(pendingNewCb).not.toBeNull();
    act(() => {
      pendingNewCb!(n);
    });
  }

  // ── test_toast_appears_on_new_notification ────────────────────────────────
  it("renders a toast when a new notification arrives", () => {
    const { container } = render(
      <NotificationProvider>
        <NotificationToaster />
      </NotificationProvider>,
    );

    pushToast(makeNotif({ id: "new-notif-1", title: "New Volume Surge" }));

    const toastStatus = container.querySelector('[role="status"]');
    expect(toastStatus).not.toBeNull();
    expect(toastStatus!.textContent).toContain("New Volume Surge");
  });

  // ── test_high_severity_pulse_class ───────────────────────────────────────
  it("high-severity toast has animate-pulse class", () => {
    const { container } = render(
      <NotificationProvider>
        <NotificationToaster />
      </NotificationProvider>,
    );

    pushToast(makeNotif({ id: "high-toast-1", severity: "high" }));

    const toast = container.querySelector('[role="status"]');
    expect(toast).not.toBeNull();
    expect(toast!.className).toContain("animate-pulse");
  });

  // ── test_ack_button_calls_ack ────────────────────────────────────────────
  it("ack function calls POST /api/notifications/{id}/ack", async () => {
    const ackImpl = async (id: string) => {
      await fetch(`/api/notifications/${id}/ack`, { method: "POST" });
    };
    let ackFn: ((id: string) => Promise<void>) | null = null;
    useNotificationsMock.mockImplementation((opts) => {
      if (opts?.onNew) pendingNewCb = opts.onNew;
      ackFn = ackImpl;
      return {
        notifications: [],
        unseenCount: 0,
        markSeen: vi.fn(),
        ack: ackImpl,
      };
    });

    render(
      <NotificationProvider>
        <NotificationToaster />
      </NotificationProvider>,
    );

    // 直接调 ack (NotificationToaster.handleAck 通过 context 取 ack), 模拟 "user 点 Ack"
    expect(ackFn).not.toBeNull();
    await act(async () => {
      await ackFn!("ack-btn-test");
    });

    const ackCalls = fetchSpy.mock.calls.filter(
      ([url, o]) =>
        typeof url === "string" &&
        url.includes("/ack") &&
        (o as RequestInit | undefined)?.method === "POST",
    );
    expect(ackCalls).toHaveLength(1);
    expect(ackCalls[0]?.[0]).toBe("/api/notifications/ack-btn-test/ack");
  });
});
