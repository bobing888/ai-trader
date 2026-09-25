import axios, { type AxiosInstance } from "axios";

const apiClient: AxiosInstance = axios.create({
  baseURL: "/api",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("[API Error]", error.response?.status, error.config?.url, error.message);
    return Promise.reject(error);
  },
);

export default apiClient;

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface KLinesResponse {
  symbol: string;
  timeframe: string;
  candles: Candle[];
  count: number;
}

export interface Trade {
  id: number;
  pair: string;
  is_open: boolean;
  open_date: string;
  close_date: string | null;
  open_rate: number | null;
  close_rate: number | null;
  amount: number | null;
  stake_amount: number;
  close_profit: number | null;
  close_profit_abs: number | null;
  exit_reason: string | null;
  strategy: string | null;
  enter_tag: string | null;
  leverage: number;
  is_short: boolean;
}

export interface TradesResponse {
  trades: Trade[];
  total_count: number;
  source: string;
}

export interface TradesSummary {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_profit_abs: number;
  profit_factor: number;
  source: string;
}

export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "1d";

export const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];

export async function fetchKLines(
  symbol: string,
  timeframe: Timeframe = "1h",
  limit = 500,
): Promise<KLinesResponse> {
  const { data } = await apiClient.get<KLinesResponse>(`/klines/${symbol}`, {
    params: { timeframe, limit },
  });
  return data;
}

export async function fetchTrades(params: {
  limit?: number;
  pair?: string;
  strategy?: string;
}): Promise<TradesResponse> {
  const { data } = await apiClient.get<TradesResponse>("/trades", { params });
  return data;
}

export async function fetchTradesSummary(): Promise<TradesSummary> {
  const { data } = await apiClient.get<TradesSummary>("/trades/stats/summary");
  return data;
}

export async function fetchHealth(): Promise<unknown> {
  const { data } = await apiClient.get("/health");
  return data;
}

export interface SymbolMeta {
  symbol: string;
  price: number;
  change_24h: number;
}

/** Fetch latest ticker for a single symbol. Falls back to zeros on error. */
export async function fetchSymbolMeta(symbol: string): Promise<SymbolMeta> {
  try {
    const { data } = await apiClient.get<SymbolMeta>(`/ticker/${symbol}`);
    return data;
  } catch {
    return { symbol, price: 0, change_24h: 0 };
  }
}

/** Batch ticker — used by Topbar to render multiple symbols at once. */
export async function fetchBatchTickers(symbols: string[]): Promise<SymbolMeta[]> {
  const { data } = await apiClient.get<{ tickers: SymbolMeta[] }>(
    "/ticker/batch",
    { params: { symbols: symbols.join(",") } },
  );
  return data.tickers ?? [];
}

// ─── Signals / Recommendations ────────────────────────────────────────────────

export type RegimeName = "bull" | "bear" | "choppy" | "crisis";

export interface RegimeInfo {
  regime: RegimeName;
  confidence: number;
  regime_probs: Record<RegimeName, number>;
  description: string;
}

export interface RecommendationSignal {
  pair: string;
  direction: "long" | "short";
  confidence: number;
  contributing_strategies: string[];
  reasons: string[];
  entry_zones: string[];
  risk_warnings: string[];
  regime: RegimeName;
  regime_confidence: number;
  generated_at: string;
}

export interface SignalResponse {
  has_signal: boolean;
  message?: string;
  signal?: RecommendationSignal;
  regime: RegimeInfo | null;
}

export interface BatchSignalItem {
  pair: string;
  has_signal: boolean;
  signal?: RecommendationSignal;
  regime: RegimeInfo | null;
}

export interface BatchSignalsResponse {
  results: BatchSignalItem[];
  ranked: BatchSignalItem[];
  count: number;
  regime_global: RegimeInfo | null;
}

/** Fetch recommendation signal for a single pair */
export async function fetchSignal(pair: string, timeframe = "1h"): Promise<SignalResponse> {
  const { data } = await apiClient.get<SignalResponse>(
    `/signals/recommend/${encodeURIComponent(pair)}`,
    { params: { timeframe } },
  );
  return data;
}

/** Fetch batch recommendation signals for multiple pairs */
export async function fetchBatchSignals(
  pairs: string[],
  timeframe = "1h",
): Promise<BatchSignalsResponse> {
  const { data } = await apiClient.get<BatchSignalsResponse>(
    "/signals/batch",
    { params: { pairs: pairs.join(","), timeframe } },
  );
  return data;
}

// ─── Strategies CRUD ─────────────────────────────────────────────────────────

export interface Strategy {
  id: number;
  name: string;
  description: string;
  strategy_type: string;
  source: string;
  parameters: Record<string, unknown>;
  code: string;
  status: string;
  weight: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyCreate {
  name: string;
  description?: string;
  strategy_type?: string;
  parameters?: Record<string, unknown>;
  code?: string;
  status?: string;
  weight?: number;
}

export interface StrategyUpdate {
  name?: string;
  description?: string;
  strategy_type?: string;
  parameters?: Record<string, unknown>;
  code?: string;
  status?: string;
  weight?: number;
}

export const STRATEGY_TYPES = ["custom", "github", "imported", "builtin"] as const;

export async function fetchStrategies(params?: {
  status?: string;
  strategy_type?: string;
  limit?: number;
  offset?: number;
}): Promise<Strategy[]> {
  const { data } = await apiClient.get<Strategy[]>("/strategies", { params });
  return data;
}

export async function fetchStrategy(id: number): Promise<Strategy> {
  const { data } = await apiClient.get<Strategy>(`/strategies/${id}`);
  return data;
}

export async function createStrategy(payload: StrategyCreate): Promise<Strategy> {
  const { data } = await apiClient.post<Strategy>("/strategies", payload);
  return data;
}

export async function updateStrategy(id: number, payload: StrategyUpdate): Promise<Strategy> {
  const { data } = await apiClient.put<Strategy>(`/strategies/${id}`, payload);
  return data;
}

export async function deleteStrategy(id: number): Promise<void> {
  await apiClient.delete(`/strategies/${id}`);
}

export async function cloneStrategy(id: number): Promise<Strategy> {
  const { data } = await apiClient.post<Strategy>(`/strategies/${id}/clone`);
  return data;
}

export async function exportStrategy(id: number): Promise<Record<string, unknown>> {
  const { data } = await apiClient.get<Record<string, unknown>>(`/strategies/${id}/export`);
  return data;
}

export async function importStrategy(payload: Record<string, unknown>): Promise<Strategy> {
  const { data } = await apiClient.post<Strategy>("/strategies/import", payload);
  return data;
}

export interface SyncStatus {
  enabled: boolean;
  interval_hours: number;
  query: string;
  limit: number;
  github_strategies_count: number;
  items: { id: number; name: string; parameters: Record<string, unknown>; updated_at: string }[];
}

export async function triggerGithubSync(): Promise<{
  status: string;
  added: number;
  skipped: number;
  total_searched: number;
  synced_at?: string;
  error?: string;
}> {
  const { data } = await apiClient.post("/strategies/sync-github");
  return data;
}

export async function fetchGithubSyncStatus(): Promise<SyncStatus> {
  const { data } = await apiClient.get<SyncStatus>("/strategies/sync-github/status");
  return data;
}

// ─── Unified Analysis ─────────────────────────────────────────────────────────

export interface RegimeInfo {
  regime: RegimeName;
  confidence: number;
  regime_probs: Record<RegimeName, number>;
  description: string;
}

export interface TrendInfo {
  adx: number;
  pdi: number;
  ndi: number;
  strength_label: string;
  direction?: "long" | "short";
}

export interface VolatilityInfo {
  current_atr_pct: number;
  current_atr?: number;
  percentile_1y: number;
  level: string;
}

export interface StatisticalInfo {
  hurst: number;
  fractal_dim: number;
  entropy: number;
  interpretation: string;
}

export interface MultiFactorInfo {
  technical: number;
  fundamental: number;
  sentiment: number;
  composite: number;
}

export interface AnalysisResponse {
  symbol: string;
  timeframe: string;
  as_of: string;
  regime: RegimeInfo;
  trend: TrendInfo;
  volatility: VolatilityInfo;
  statistical: StatisticalInfo;
  multifactor: MultiFactorInfo;
}

export async function fetchAnalysis(symbol: string, timeframe = "1h", limit = 500): Promise<AnalysisResponse> {
  const { data } = await apiClient.get<AnalysisResponse>(`/analysis/${symbol}`, {
    params: { timeframe, limit },
  });
  return data;
}
