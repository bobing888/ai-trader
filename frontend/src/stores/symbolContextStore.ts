/**
 * 全局当前 symbol 状态 — K 线页写入，RightSidebar 读取
 * 让合约计算器等工具栏组件能跨页面共享当前交易对 + 最近 K 线
 */

import { create } from "zustand";

import type { Candle } from "@/lib/api";

interface SymbolContextState {
  symbol: string;
  timeframe: string;
  candles: Candle[];
  markPrice: number;
  setContext: (ctx: { symbol: string; timeframe: string; candles: Candle[] }) => void;
  clearContext: () => void;
}

export const useSymbolContext = create<SymbolContextState>((set) => ({
  symbol: "",
  timeframe: "",
  candles: [],
  markPrice: 0,
  setContext: ({ symbol, timeframe, candles }) => {
    const markPrice = candles.length > 0 ? candles[candles.length - 1].close : 0;
    set({ symbol, timeframe, candles, markPrice });
  },
  clearContext: () => set({ symbol: "", timeframe: "", candles: [], markPrice: 0 }),
}));
