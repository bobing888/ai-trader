import { describe, expect, it } from "vitest";
import {
  BacktestRequestSchema,
  BacktestResponseSchema,
  BacktestTradeSchema,
} from "@/lib/backtestApi";

describe("BacktestRequestSchema", () => {
  it("accepts minimal valid request", () => {
    const r = BacktestRequestSchema.parse({
      symbol: "BTC-USDT",
      timeframe: "1h",
      strategies: ["MomentumStrategy"],
    });
    expect(r.symbol).toBe("BTC-USDT");
    expect(r.timeframe).toBe("1h");
    expect(r.days).toBe(30); // default
  });

  it("rejects empty strategies", () => {
    expect(() =>
      BacktestRequestSchema.parse({
        symbol: "BTC-USDT",
        timeframe: "1h",
        strategies: [],
      })
    ).toThrow();
  });

  it("rejects days > 365", () => {
    expect(() =>
      BacktestRequestSchema.parse({
        symbol: "BTC-USDT",
        timeframe: "1h",
        strategies: ["MomentumStrategy"],
        days: 1000,
      })
    ).toThrow();
  });
});

describe("BacktestResponseSchema", () => {
  const validResponse = {
    run_id: 1,
    summary: {
      total_trades: 10,
      hit_rate: 0.6,
      net_pnl_pct: 0.05,
      sharpe_ratio: 1.5,
      max_drawdown_pct: -0.02,
      started_at: "2026-10-01T00:00:00Z",
      finished_at: "2026-10-01T00:01:00Z",
      status: "done",
    },
    equity_curve: [{ ts: "2026-10-01T00:00:00Z", equity: 1.0 }],
    trades: [
      {
        id: 1,
        strategy_name: "MomentumStrategy",
        entry_time: "2026-10-01T00:00:00Z",
        entry_price: 100,
        exit_time: "2026-10-01T01:00:00Z",
        exit_price: 101,
        raw_confidence: 0.7,
        calibrated_confidence: 0.62,
        net_pnl_pct: 0.01,
        outcome: "HIT_TP" as const,
        holding_minutes: 60,
      },
    ],
  };

  it("parses valid response", () => {
    expect(() => BacktestResponseSchema.parse(validResponse)).not.toThrow();
  });

  it("rejects missing summary", () => {
    const invalid = { run_id: 1, equity_curve: [], trades: [] };
    expect(() => BacktestResponseSchema.parse(invalid)).toThrow();
  });

  it("rejects invalid outcome enum", () => {
    const bad = {
      ...validResponse,
      trades: [
        {
          ...validResponse.trades[0],
          outcome: "WRONG_OUTCOME",
        },
      ],
    };
    expect(() => BacktestResponseSchema.parse(bad)).toThrow();
  });
});

describe("BacktestTradeSchema", () => {
  it("accepts nullable calibrated_confidence (cold start)", () => {
    const t = BacktestTradeSchema.parse({
      id: 1,
      strategy_name: "MomentumStrategy",
      entry_time: "2026-10-01T00:00:00Z",
      entry_price: 100,
      exit_time: "2026-10-01T01:00:00Z",
      exit_price: 99,
      raw_confidence: 0.5,
      calibrated_confidence: null,
      net_pnl_pct: -0.01,
      outcome: "HIT_SL",
      holding_minutes: 60,
    });
    expect(t.calibrated_confidence).toBeNull();
  });
});