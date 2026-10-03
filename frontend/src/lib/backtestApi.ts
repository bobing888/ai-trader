/**
 * Backtest API client — Phase 1 signal credibility.
 *
 * Wraps POST /api/backtest + GET /api/backtest/runs + GET /api/backtest/runs/{id}.
 * Uses zod runtime validation to catch contract drift early.
 */
import { z } from "zod";

export const BacktestRequestSchema = z.object({
  symbol: z.string().min(1),
  timeframe: z.enum(["1m", "5m", "15m", "1h", "4h", "1d"]),
  strategies: z.array(z.string()).min(1),
  days: z.number().int().min(1).max(365).default(30),
  fee_taker_bps: z.number().min(0).default(8.0),
  slippage_bps: z.number().min(0).default(5.0),
  min_confidence: z.number().min(0).max(1).default(0.6),
  target_pct: z.number().gt(0).lt(0.5).default(0.005),
  stop_pct: z.number().gt(0).lt(0.5).default(0.003),
  max_hold_minutes: z.number().int().min(1).max(1440).default(60),
});

export type BacktestRequest = z.infer<typeof BacktestRequestSchema>;

export const BacktestTradeSchema = z.object({
  id: z.number(),
  strategy_name: z.string(),
  entry_time: z.string(),
  entry_price: z.number(),
  exit_time: z.string(),
  exit_price: z.number(),
  raw_confidence: z.number(),
  calibrated_confidence: z.number().nullable(),
  net_pnl_pct: z.number(),
  outcome: z.enum(["HIT_TP", "HIT_SL", "EXPIRED", "HOLD"]),
  holding_minutes: z.number(),
});

export const BacktestSummarySchema = z.object({
  total_trades: z.number(),
  hit_rate: z.number(),
  net_pnl_pct: z.number(),
  sharpe_ratio: z.number(),
  max_drawdown_pct: z.number(),
  started_at: z.string(),
  finished_at: z.string(),
  status: z.string(),
});

export const BacktestResponseSchema = z.object({
  run_id: z.number(),
  summary: BacktestSummarySchema,
  equity_curve: z.array(z.object({ ts: z.string(), equity: z.number() })),
  trades: z.array(BacktestTradeSchema),
});

export type BacktestResponse = z.infer<typeof BacktestResponseSchema>;
export type BacktestSummary = z.infer<typeof BacktestSummarySchema>;
export type BacktestTrade = z.infer<typeof BacktestTradeSchema>;

export async function runBacktest(req: BacktestRequest): Promise<BacktestResponse> {
  const validated = BacktestRequestSchema.parse(req);
  const resp = await fetch("/api/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(validated),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Backtest failed (${resp.status}): ${err}`);
  }
  return BacktestResponseSchema.parse(await resp.json());
}

export async function listBacktestRuns(symbol?: string, limit = 20): Promise<unknown[]> {
  const url = symbol
    ? `/api/backtest/runs?symbol=${encodeURIComponent(symbol)}&limit=${limit}`
    : `/api/backtest/runs?limit=${limit}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`List runs failed (${resp.status})`);
  return resp.json();
}

export async function getBacktestRun(runId: number): Promise<BacktestResponse> {
  const resp = await fetch(`/api/backtest/runs/${runId}`);
  if (!resp.ok) throw new Error(`Get run failed (${resp.status})`);
  return BacktestResponseSchema.parse(await resp.json());
}