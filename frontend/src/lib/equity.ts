import type { Trade } from "@/lib/api";

export interface EquityPoint {
  /** ISO timestamp of the trade close */
  time: string;
  /** Cumulative profit at this point (sum of all closed trades up to and including this trade) */
  cumulative: number;
  /** Individual trade profit that landed at this point */
  tradeProfit: number;
  /** Trade id (for cross-linking back to the trades table) */
  tradeId: number;
  /** Pair for tooltip display */
  pair: string;
}

export interface EquityStats {
  /** Total realized P&L (sum of close_profit_abs for closed trades) */
  total: number;
  /** Highest equity peak */
  peak: number;
  /** Lowest equity trough */
  trough: number;
  /** Max drawdown as a positive percentage (peak - trough / peak) */
  maxDrawdownPct: number;
  /** Date of the highest peak (ISO) */
  peakAt: string | null;
  /** Date of the lowest trough (ISO) */
  troughAt: string | null;
  /** Win rate as a percentage */
  winRate: number;
  /** Profit factor (gross wins / gross losses), NaN if no losses */
  profitFactor: number;
  /** Average winning trade P&L */
  avgWin: number;
  /** Average losing trade P&L (negative number) */
  avgLoss: number;
  /** Best single trade P&L */
  bestTrade: number;
  /** Worst single trade P&L */
  worstTrade: number;
  /** Number of winning trades */
  wins: number;
  /** Number of losing trades */
  losses: number;
  /** Number of closed trades in window */
  closedCount: number;
}

/** Build a cumulative P&L curve from a list of closed trades. */
export function buildEquityCurve(trades: Trade[]): EquityPoint[] {
  const closed = trades
    .filter((t) => !t.is_open && t.close_date && t.close_profit_abs !== null)
    .sort((a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime());

  let running = 0;
  return closed.map((t) => {
    running += t.close_profit_abs ?? 0;
    return {
      time: t.close_date!,
      cumulative: running,
      tradeProfit: t.close_profit_abs ?? 0,
      tradeId: t.id,
      pair: t.pair,
    };
  });
}

/** Aggregate stats over the provided (closed) trades. */
export function computeEquityStats(trades: Trade[]): EquityStats {
  const closed = trades.filter((t) => !t.is_open && t.close_profit_abs !== null);
  const profits = closed.map((t) => t.close_profit_abs as number);
  const winsArr = profits.filter((p) => p > 0);
  const lossesArr = profits.filter((p) => p < 0);

  const wins = winsArr.length;
  const losses = lossesArr.length;
  const total = profits.reduce((s, p) => s + p, 0);

  const grossProfit = winsArr.reduce((s, p) => s + p, 0);
  const grossLoss = Math.abs(lossesArr.reduce((s, p) => s + p, 0));
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;

  const peak = profits.length > 0 ? Math.max(...profits) : 0;
  const trough = profits.length > 0 ? Math.min(...profits) : 0;

  const sortedByDate = [...closed].sort(
    (a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime(),
  );
  let running = 0;
  let peakEquity = Number.NEGATIVE_INFINITY;
  let troughEquity = Number.POSITIVE_INFINITY;
  let peakAt: string | null = null;
  let troughAt: string | null = null;
  for (const t of sortedByDate) {
    running += t.close_profit_abs ?? 0;
    if (running > peakEquity) {
      peakEquity = running;
      peakAt = t.close_date!;
    }
    if (running < troughEquity) {
      troughEquity = running;
      troughAt = t.close_date!;
    }
  }
  const maxDrawdownPct =
    Number.isFinite(peakEquity) && peakEquity > 0
      ? ((peakEquity - (Number.isFinite(troughEquity) ? troughEquity : peakEquity)) / peakEquity) * 100
      : 0;

  return {
    total,
    peak,
    trough,
    maxDrawdownPct,
    peakAt,
    troughAt,
    winRate: closed.length > 0 ? (wins / closed.length) * 100 : 0,
    profitFactor,
    avgWin: wins > 0 ? grossProfit / wins : 0,
    avgLoss: losses > 0 ? -grossLoss / losses : 0,
    bestTrade: peak,
    worstTrade: trough,
    wins,
    losses,
    closedCount: closed.length,
  };
}

/** Window a closed-trade series to the last N days. */
export function windowByDays(curve: EquityPoint[], days: number): EquityPoint[] {
  if (curve.length === 0) return curve;
  const cutoff = new Date(curve[curve.length - 1].time).getTime() - days * 86_400_000;
  return curve.filter((p) => new Date(p.time).getTime() >= cutoff);
}
