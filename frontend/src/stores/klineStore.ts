import { create } from "zustand";

import type { Timeframe } from "@/lib/api";

interface KlineStoreState {
  symbol: string;
  timeframe: Timeframe;
  setSymbol: (symbol: string) => void;
  setTimeframe: (tf: Timeframe) => void;
  hydrateFromSearch: (search: URLSearchParams) => void;
}

const ALLOWED_TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];

function safeTimeframe(v: string | null): Timeframe | null {
  if (!v) return null;
  return ALLOWED_TIMEFRAMES.includes(v as Timeframe) ? (v as Timeframe) : null;
}

export const useKlineStore = create<KlineStoreState>((set) => ({
  symbol: "BTCUSDT",
  timeframe: "1h",
  setSymbol: (symbol) => set({ symbol }),
  setTimeframe: (timeframe) => set({ timeframe }),
  /**
   * Apply `?symbol=...&timeframe=...` from the URL into the store.
   * Invalid / missing values are ignored (keep current store value).
   */
  hydrateFromSearch: (search) => {
    const symbol = search.get("symbol");
    const timeframe = safeTimeframe(search.get("timeframe"));
    set((s) => ({
      symbol: symbol && symbol.length > 0 ? symbol : s.symbol,
      timeframe: timeframe ?? s.timeframe,
    }));
  },
}));
