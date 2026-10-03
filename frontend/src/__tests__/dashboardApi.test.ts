import { describe, expect, it } from "vitest";

import {
  OverviewResponseSchema,
  OverviewItemSchema,
  SignalSummarySchema,
} from "@/lib/dashboardApi";

const validSignal = {
  direction: "long",
  confidence: 0.72,
  calibrated_confidence: 0.68,
  quality: "high",
  timeframe: "1h",
  entry_zone_first: "现价下方 2-3% 分批建仓",
  take_profit_1: 68560.0,
  stop_loss: 67200.0,
  risk_reward_ratio: 1.33,
  next_predicted_move: "看多 ↑ 0.5% (high)",
};

const validItem = {
  symbol: "BTC-USDT",
  price: 67890.12,
  change_24h_pct: 1.45,
  signal: validSignal,
  degraded: false,
  error: null,
};

const validResponse = {
  items: [validItem],
  timeframe: "1h",
  source: "okx",
  generated_at: "2026-10-03T03:04:05Z",
};

describe("dashboardApi zod schemas", () => {
  it("parses a valid SignalSummary", () => {
    expect(() => SignalSummarySchema.parse(validSignal)).not.toThrow();
  });

  it("rejects unknown quality values", () => {
    expect(() =>
      SignalSummarySchema.parse({ ...validSignal, quality: "unknown" }),
    ).toThrow();
  });

  it("rejects out-of-range confidence", () => {
    expect(() =>
      SignalSummarySchema.parse({ ...validSignal, confidence: 1.5 }),
    ).toThrow();
    expect(() =>
      SignalSummarySchema.parse({ ...validSignal, confidence: -0.1 }),
    ).toThrow();
  });

  it("allows null for optional signal fields", () => {
    const ok = SignalSummarySchema.parse({
      direction: "short",
      confidence: 0.5,
      quality: "low",
      timeframe: "1h",
      risk_reward_ratio: 0.0,
      next_predicted_move: "看空 ↓ 0.3% (low)",
      calibrated_confidence: null,
      entry_zone_first: null,
      take_profit_1: null,
      stop_loss: null,
    });
    expect(ok.calibrated_confidence).toBeNull();
  });

  it("parses OverviewItem with signal null (no consensus)", () => {
    const ok = OverviewItemSchema.parse({
      ...validItem,
      signal: null,
    });
    expect(ok.signal).toBeNull();
  });

  it("parses OverviewItem degraded", () => {
    const ok = OverviewItemSchema.parse({
      symbol: "DOGE-USDT",
      price: 0,
      change_24h_pct: 0,
      signal: null,
      degraded: true,
      error: "rate limit",
    });
    expect(ok.degraded).toBe(true);
    expect(ok.error).toBe("rate limit");
  });

  it("parses full OverviewResponse", () => {
    expect(() => OverviewResponseSchema.parse(validResponse)).not.toThrow();
  });

  it("rejects malformed OverviewResponse", () => {
    expect(() =>
      OverviewResponseSchema.parse({ ...validResponse, timeframe: 123 }),
    ).toThrow();
  });
});