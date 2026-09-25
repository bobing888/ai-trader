import { describe, expect, it } from "vitest";

import type { Trade } from "@/lib/api";
import { buildEquityCurve, computeEquityStats, windowByDays } from "@/lib/equity";

const makeTrade = (overrides: Partial<Trade>): Trade => ({
  id: 1,
  pair: "BTCUSDT",
  is_open: false,
  open_date: "2026-09-01T00:00:00Z",
  close_date: "2026-09-01T01:00:00Z",
  open_rate: 50000,
  close_rate: 50100,
  amount: 0.1,
  stake_amount: 5000,
  close_profit: 0.2,
  close_profit_abs: 100,
  exit_reason: "roi",
  strategy: "StrategyA",
  enter_tag: "tag1",
  leverage: 1,
  is_short: false,
  ...overrides,
});

describe("buildEquityCurve", () => {
  it("returns empty array when no closed trades", () => {
    expect(buildEquityCurve([])).toEqual([]);
  });

  it("skips open trades", () => {
    const trades = [
      makeTrade({ id: 1, is_open: true, close_profit_abs: null, close_date: null }),
    ];
    expect(buildEquityCurve(trades)).toEqual([]);
  });

  it("sorts by close_date ascending and accumulates", () => {
    const trades = [
      makeTrade({ id: 1, close_date: "2026-09-03T00:00:00Z", close_profit_abs: 50 }),
      makeTrade({ id: 2, close_date: "2026-09-01T00:00:00Z", close_profit_abs: 100 }),
      makeTrade({ id: 3, close_date: "2026-09-02T00:00:00Z", close_profit_abs: -25 }),
    ];
    const curve = buildEquityCurve(trades);
    expect(curve).toHaveLength(3);
    expect(curve[0].tradeId).toBe(2);
    expect(curve[0].cumulative).toBe(100);
    expect(curve[1].tradeId).toBe(3);
    expect(curve[1].cumulative).toBe(75);
    expect(curve[2].tradeId).toBe(1);
    expect(curve[2].cumulative).toBe(125);
  });
});

describe("computeEquityStats", () => {
  it("returns zeros for empty trades", () => {
    const stats = computeEquityStats([]);
    expect(stats.total).toBe(0);
    expect(stats.winRate).toBe(0);
    expect(stats.profitFactor).toBe(0);
    expect(stats.closedCount).toBe(0);
  });

  it("computes win rate, profit factor, max drawdown correctly", () => {
    const trades = [
      makeTrade({ id: 1, close_profit_abs: 100, close_date: "2026-09-01T00:00:00Z" }),
      makeTrade({ id: 2, close_profit_abs: -50, close_date: "2026-09-02T00:00:00Z" }),
      makeTrade({ id: 3, close_profit_abs: 200, close_date: "2026-09-03T00:00:00Z" }),
      makeTrade({ id: 4, close_profit_abs: -25, close_date: "2026-09-04T00:00:00Z" }),
    ];
    const stats = computeEquityStats(trades);
    expect(stats.total).toBe(225);
    expect(stats.wins).toBe(2);
    expect(stats.losses).toBe(2);
    expect(stats.winRate).toBe(50);
    // grossProfit = 300, grossLoss = 75 → PF = 4
    expect(stats.profitFactor).toBeCloseTo(4, 5);
    expect(stats.avgWin).toBe(150);
    expect(stats.avgLoss).toBe(-37.5);
    expect(stats.bestTrade).toBe(200);
    expect(stats.worstTrade).toBe(-50);
    // Equity path: 100, 50, 250, 225 → peak=250, trough=50 → drawdown = 80%
    expect(stats.maxDrawdownPct).toBeCloseTo(80, 1);
  });

  it("handles all-winning trades (no losses)", () => {
    const trades = [
      makeTrade({ id: 1, close_profit_abs: 50 }),
      makeTrade({ id: 2, close_profit_abs: 75 }),
    ];
    const stats = computeEquityStats(trades);
    expect(stats.profitFactor).toBe(Infinity);
    expect(stats.avgLoss).toBe(0);
  });

  it("handles all-losing trades (no wins)", () => {
    const trades = [
      makeTrade({ id: 1, close_profit_abs: -30 }),
      makeTrade({ id: 2, close_profit_abs: -20 }),
    ];
    const stats = computeEquityStats(trades);
    expect(stats.profitFactor).toBe(0);
    expect(stats.avgWin).toBe(0);
    expect(stats.total).toBe(-50);
  });

  it("ignores open trades", () => {
    const trades = [
      makeTrade({ id: 1, close_profit_abs: 100 }),
      makeTrade({ id: 2, is_open: true, close_profit_abs: null, close_date: null }),
    ];
    const stats = computeEquityStats(trades);
    expect(stats.closedCount).toBe(1);
    expect(stats.total).toBe(100);
  });
});

describe("windowByDays", () => {
  const trades = [
    makeTrade({ id: 1, close_date: "2026-08-20T00:00:00Z", close_profit_abs: 50 }),
    makeTrade({ id: 2, close_date: "2026-09-01T00:00:00Z", close_profit_abs: 100 }),
    makeTrade({ id: 3, close_date: "2026-09-15T00:00:00Z", close_profit_abs: -30 }),
  ];

  it("filters to recent N days from the most recent point", () => {
    const curve = buildEquityCurve(trades);
    const windowed = windowByDays(curve, 30);
    // last point is 2026-09-15, cutoff = 2026-08-16, so id=1 (08-20) should be in window
    expect(windowed).toHaveLength(3);
  });

  it("returns empty when window is too small", () => {
    const curve = buildEquityCurve(trades);
    const windowed = windowByDays(curve, 5);
    // cutoff = 2026-09-10, only id=3 qualifies
    expect(windowed).toHaveLength(1);
    expect(windowed[0].tradeId).toBe(3);
  });
});
