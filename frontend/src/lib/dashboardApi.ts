import { z } from "zod";

import apiClient from "@/lib/api";

export const SignalSummarySchema = z.object({
  direction: z.enum(["long", "short"]),
  confidence: z.number().min(0).max(1),
  calibrated_confidence: z.number().min(0).max(1).nullable(),
  quality: z.enum(["high", "medium", "low", "reject"]),
  timeframe: z.string(),
  entry_zone_first: z.string().nullable(),
  take_profit_1: z.number().nullable(),
  stop_loss: z.number().nullable(),
  risk_reward_ratio: z.number().min(0),
  next_predicted_move: z.string(),
});

export const OverviewItemSchema = z.object({
  symbol: z.string(),
  price: z.number().min(0),
  change_24h_pct: z.number(),
  signal: SignalSummarySchema.nullable(),
  degraded: z.boolean(),
  error: z.string().nullable(),
});

export const OverviewResponseSchema = z.object({
  items: z.array(OverviewItemSchema),
  timeframe: z.string(),
  source: z.string(),
  generated_at: z.string(),
});

export type SignalSummary = z.infer<typeof SignalSummarySchema>;
export type OverviewItem = z.infer<typeof OverviewItemSchema>;
export type OverviewResponse = z.infer<typeof OverviewResponseSchema>;

export const DASHBOARD_DEFAULT_SYMBOLS = [
  "BTC-USDT",
  "ETH-USDT",
  "SOL-USDT",
] as const;

export async function fetchDashboardOverview(
  symbols: readonly string[] = DASHBOARD_DEFAULT_SYMBOLS,
  timeframe: string = "1h",
): Promise<OverviewResponse> {
  const params = new URLSearchParams({
    symbols: symbols.join(","),
    timeframe,
  });
  const resp = await apiClient.get(`/dashboard/overview?${params.toString()}`);
  return OverviewResponseSchema.parse(resp.data);
}