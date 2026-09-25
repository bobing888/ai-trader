import { Route, BrowserRouter as Router, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandPaletteProvider } from "@/components/ui/CommandPalette";
import { ToastProvider } from "@/components/ui/Toast";
import { BacktestPage } from "@/pages/BacktestPage";
import { FuturesPage } from "@/pages/FuturesPage";
import { KlinePage } from "@/pages/KlinePage";
import { RecommendationsPage } from "@/pages/RecommendationsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { StrategyPage } from "@/pages/StrategyPage";
import { TradesPage } from "@/pages/TradesPage";

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <Router>
          <CommandPaletteProvider>
            <AppLayout>
              <Routes>
                <Route path="/" element={<KlinePage />} />
                <Route path="/kline" element={<KlinePage />} />
                <Route path="/recommendations" element={<RecommendationsPage />} />
                <Route path="/trades" element={<TradesPage />} />
                <Route path="/backtest" element={<BacktestPage />} />
                <Route path="/strategies" element={<StrategyPage />} />
                <Route path="/futures" element={<FuturesPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </AppLayout>
          </CommandPaletteProvider>
        </Router>
      </ToastProvider>
    </ErrorBoundary>
  );
}
