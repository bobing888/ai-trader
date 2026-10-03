import { Route, BrowserRouter as Router, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { NotificationProvider } from "@/components/notifications/NotificationProvider";
import { CommandPaletteProvider } from "@/components/ui/CommandPalette";
import { ToastProvider } from "@/components/ui/Toast";
import { AnalysisPage } from "@/pages/AnalysisPage";
import { BacktestPage } from "@/pages/BacktestPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { FollowsPage } from "@/pages/FollowsPage";
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
        <NotificationProvider>
          <Router>
            <CommandPaletteProvider>
              <AppLayout>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/analysis" element={<AnalysisPage />} />
                  <Route path="/recommendations" element={<RecommendationsPage />} />
                  <Route path="/trades" element={<TradesPage />} />
                  <Route path="/follows" element={<FollowsPage />} />
                  <Route path="/backtest" element={<BacktestPage />} />
                  <Route path="/strategies" element={<StrategyPage />} />
                  <Route path="/futures" element={<FuturesPage />} />
                  <Route path="/chart" element={<KlinePage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Routes>
              </AppLayout>
            </CommandPaletteProvider>
          </Router>
        </NotificationProvider>
      </ToastProvider>
    </ErrorBoundary>
  );
}
