import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import i18n from "@/i18n";
import App from "@/App";

const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={i18n}>{component}</I18nextProvider>
    </QueryClientProvider>,
  );
};

describe("App", () => {
  it("renders the brand block", () => {
    renderWithProviders(<App />);
    // Sidebar logo + tagline should be visible regardless of locale.
    // Both desktop + mobile drawers render the brand, so use getAllByText.
    expect(screen.getAllByText("AI 交易助手").length).toBeGreaterThan(0);
    expect(screen.getAllByText("智能加密货币交易信号").length).toBeGreaterThan(0);
  });

  it("renders all primary nav items", () => {
    renderWithProviders(<App />);
    // App renders both desktop sidebar and mobile drawer; assert at least one of each.
    expect(screen.getAllByTestId("nav-kline").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("nav-rec").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("nav-trades").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("nav-backtest").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("nav-settings").length).toBeGreaterThan(0);
  });
});
