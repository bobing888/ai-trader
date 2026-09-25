import { useTranslation } from "react-i18next";
import { Search, Bell, Menu } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ThemeToggle, useTheme } from "@/components/ui/ThemeToggle";
import { useCommandPalette } from "@/components/ui/CommandPalette";
import { cn } from "@/lib/utils";
import { fetchBatchTickers } from "@/lib/api";
import { useKlineStore } from "@/stores/klineStore";

interface TopbarProps {
  onMenuClick?: () => void;
}

const TOPBAR_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];

export function Topbar({ onMenuClick }: TopbarProps) {
  const { t } = useTranslation();
  const { theme, toggle } = useTheme();
  const openCommandPalette = useCommandPalette();
  const currentSymbol = useKlineStore((s) => s.symbol);
  const setSymbol = useKlineStore((s) => s.setSymbol);

  const { data: tickers = [] } = useQuery({
    queryKey: ["topbar-tickers", TOPBAR_SYMBOLS],
    queryFn: () => fetchBatchTickers(TOPBAR_SYMBOLS),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  return (
    <header className="h-16 border-b border-[rgba(255,240,220,0.06)] bg-bg-primary/80 backdrop-blur-md flex items-center justify-between px-4 md:px-6 sticky top-0 z-10">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="p-2 -ml-2 rounded-full text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors lg:hidden"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}
        <button
          onClick={openCommandPalette}
          className={cn(
            "relative max-w-md w-full h-10 pl-10 pr-12 rounded-full text-left",
            "bg-bg-secondary border border-[rgba(255,240,220,0.06)]",
            "text-sm text-text-tertiary",
            "hover:border-[rgba(255,240,220,0.16)] hover:bg-bg-tertiary",
            "focus:outline-none focus:border-accent/40 transition-colors",
            "hidden md:block",
          )}
          data-testid="topbar-search"
          aria-label={t("common.search")}
        >
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
          <span className="block truncate">{t("common.search")}</span>
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden md:inline-flex h-5 px-1.5 items-center rounded-md bg-bg-tertiary border border-[rgba(255,240,220,0.06)] text-[10px] font-medium text-text-tertiary">
            ⌘K
          </kbd>
        </button>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="hidden md:flex items-center gap-1.5">
          {TOPBAR_SYMBOLS.map((sym) => (
            <MarketPill
              key={sym}
              symbol={sym}
              ticker={tickers.find((t) => t.symbol === sym)}
              active={currentSymbol === sym}
              onSelect={() => setSymbol(sym)}
            />
          ))}
        </div>

        <div className="hidden xl:block w-px h-5 bg-[rgba(255,240,220,0.08)] mx-1" />

        <div className="flex items-center gap-1.5 h-8 px-3 rounded-full bg-bg-tertiary border border-[rgba(255,240,220,0.06)]">
          <span className="relative flex w-1.5 h-1.5">
            <span className="absolute inline-flex w-full h-full rounded-full bg-bull opacity-50 animate-pulse-live" />
            <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-bull" />
          </span>
          <span className="text-[11px] font-medium text-text-secondary tracking-wide">LIVE</span>
        </div>

        <ThemeToggle theme={theme} onToggle={toggle} />

        <button
          className="w-9 h-9 rounded-full bg-bg-tertiary border border-[rgba(255,240,220,0.06)] flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-elevated active:scale-95 transition-all"
          aria-label="Notifications"
        >
          <Bell className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}

interface MarketPillProps {
  symbol: string;
  ticker?: { symbol: string; price: number; change_24h: number };
  active: boolean;
  onSelect: () => void;
}

function MarketPill({ symbol, ticker, active, onSelect }: MarketPillProps) {
  const change = ticker?.change_24h ?? 0;
  const positive = change >= 0;
  const label = symbol.replace("USDT", "");
  return (
    <button
      onClick={onSelect}
      data-testid={`topbar-pill-${label}`}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-1.5 h-8 px-2.5 rounded-full",
        "border transition-all active:scale-[0.97]",
        active
          ? "bg-accent/10 border-accent/30 text-text-primary"
          : "bg-bg-tertiary border-[rgba(255,240,220,0.06)] text-text-secondary hover:text-text-primary hover:bg-bg-elevated hover:border-[rgba(255,240,220,0.12)]",
      )}
    >
      <span className="text-[11px] font-semibold tracking-tight">{label}</span>
      <span className={cn("text-[11px] font-medium tabular-nums", positive ? "text-bull" : "text-bear")}>
        {ticker
          ? `${positive ? "+" : ""}${change.toFixed(2)}%`
          : "—"}
      </span>
    </button>
  );
}
