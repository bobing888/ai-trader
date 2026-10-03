import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";

import i18n from "@/i18n";
import { SymbolCard } from "@/components/Dashboard/SymbolCard";
import type { OverviewItem } from "@/lib/dashboardApi";

const wrap = (ui: React.ReactElement) => (
  <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
);

const baseItem: OverviewItem = {
  symbol: "BTC-USDT",
  price: 67890.12,
  change_24h_pct: 1.45,
  signal: null,
  degraded: false,
  error: null,
};

describe("SymbolCard", () => {
  it("renders no-signal state with price and 24h change", () => {
    render(wrap(<SymbolCard item={baseItem} />));
    expect(screen.getByTestId("symbol-card-no-signal")).toBeDefined();
    // BTC 去后缀显示
    expect(screen.getByText("BTC")).toBeDefined();
    // 价格
    expect(screen.getByText("$67,890.12")).toBeDefined();
    // 24h 正涨
    expect(screen.getByText("+1.45%")).toBeDefined();
    // 观望
    expect(screen.getByText("观望")).toBeDefined();
  });

  it("renders with-signal state showing direction, quality, confidence bar, TP/SL/R:R", () => {
    const item: OverviewItem = {
      ...baseItem,
      signal: {
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
      },
    };
    render(wrap(<SymbolCard item={item} />));
    expect(screen.getByTestId("symbol-card-with-signal")).toBeDefined();
    // 做多徽章
    expect(screen.getByText("做多")).toBeDefined();
    // 高质量徽章
    expect(screen.getByText("高质量")).toBeDefined();
    // 置信度
    expect(screen.getByText("72%")).toBeDefined();
    // 预期走势
    expect(screen.getByText(/看多/)).toBeDefined();
    // TP / SL / R:R
    expect(screen.getByText("TP1")).toBeDefined();
    expect(screen.getByText("SL")).toBeDefined();
    expect(screen.getByText("R:R")).toBeDefined();
    // 负 change 渲染红色
  });

  it("renders short direction with 做空 badge", () => {
    const item: OverviewItem = {
      ...baseItem,
      change_24h_pct: -2.5,
      signal: {
        direction: "short",
        confidence: 0.6,
        calibrated_confidence: null,
        quality: "medium",
        timeframe: "4h",
        entry_zone_first: null,
        take_profit_1: null,
        stop_loss: null,
        risk_reward_ratio: 0.0,
        next_predicted_move: "看空 ↓ 0.4% (medium)",
      },
    };
    render(wrap(<SymbolCard item={item} />));
    expect(screen.getByText("做空")).toBeDefined();
    expect(screen.getByText("中等")).toBeDefined();
    expect(screen.getByText("-2.50%")).toBeDefined();
  });

  it("renders degraded state with error message", () => {
    const item: OverviewItem = {
      ...baseItem,
      price: 0,
      change_24h_pct: 0,
      degraded: true,
      error: "rate limit",
    };
    render(wrap(<SymbolCard item={item} />));
    expect(screen.getByTestId("symbol-card-degraded")).toBeDefined();
    expect(screen.getByText(/rate limit/)).toBeDefined();
  });

  it("invokes onJump with symbol when clicked", () => {
    const onJump = vi.fn();
    const item: OverviewItem = {
      ...baseItem,
      symbol: "ETH-USDT",
    };
    render(wrap(<SymbolCard item={item} onJump={onJump} />));
    fireEvent.click(screen.getByTestId("symbol-card-no-signal"));
    expect(onJump).toHaveBeenCalledWith("ETH-USDT");
    expect(onJump).toHaveBeenCalledTimes(1);
  });

  it("renders price with low-precision format for small values", () => {
    const item: OverviewItem = {
      ...baseItem,
      symbol: "DOGE-USDT",
      price: 0.1234,
    };
    render(wrap(<SymbolCard item={item} />));
    expect(screen.getByText("$0.1234")).toBeDefined();
  });
});