import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Search, TrendingUp, TrendingDown } from "lucide-react";

import type { Timeframe } from "@/lib/api";
import { TIMEFRAMES, fetchSymbolMeta } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface SymbolPickerProps {
  symbol: string;
  timeframe: Timeframe;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange?: (tf: Timeframe) => void;
}

interface SymbolMeta {
  symbol: string;
  price: number;
  change24h: number;
}

const FALLBACK_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"];

export function SymbolPicker({
  symbol,
  timeframe,
  onSymbolChange,
  onTimeframeChange,
}: SymbolPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [meta, setMeta] = useState<Record<string, SymbolMeta>>({});
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Fetch meta for all symbols when dropdown opens
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void Promise.all(
      FALLBACK_SYMBOLS.map((s) =>
        fetchSymbolMeta(s)
          .then((m) => ({ symbol: s, price: m.price, change24h: m.change_24h }))
          .catch(() => ({ symbol: s, price: 0, change24h: 0 })),
      ),
    ).then((results) => {
      if (cancelled) return;
      setMeta(Object.fromEntries(results.map((r) => [r.symbol, r])));
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const filtered = FALLBACK_SYMBOLS.filter((s) =>
    s.toLowerCase().includes(search.toLowerCase()),
  );

  const currentMeta = meta[symbol];

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Symbol picker */}
      <div className="relative" ref={containerRef}>
        <button
          onClick={() => setOpen((p) => !p)}
          data-testid="symbol-select"
          className={cn(
            "h-10 pl-4 pr-10 rounded-full cursor-pointer relative",
            "bg-bg-secondary border border-[rgba(255,240,220,0.08)]",
            "text-sm font-semibold text-text-primary",
            "hover:border-[rgba(255,240,220,0.16)] hover:bg-bg-tertiary",
            "active:scale-[0.98] transition-all",
            open && "border-accent/40",
          )}
        >
          <span className="inline-flex items-center gap-2">
            <span>{symbol}</span>
            {currentMeta && (
              <span
                className={cn(
                  "text-[11px] font-medium tabular-nums",
                  currentMeta.change24h >= 0 ? "text-bull" : "text-bear",
                )}
              >
                {currentMeta.change24h >= 0 ? "+" : ""}
                {currentMeta.change24h.toFixed(2)}%
              </span>
            )}
          </span>
          <ChevronDown
            className={cn(
              "absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary transition-transform",
              open && "rotate-180",
            )}
          />
        </button>

        {open && (
          <div
            className={cn(
              "absolute top-12 right-0 z-30 w-80 rounded-2xl",
              "bg-bg-secondary border border-[rgba(255,240,220,0.08)]",
              "shadow-2xl shadow-black/40 overflow-hidden",
              "animate-slide-up",
            )}
          >
            {/* Search */}
            <div className="p-3 border-b border-[rgba(255,240,220,0.06)]">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-tertiary" />
                <input
                  autoFocus
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索币种…"
                  className={cn(
                    "w-full h-9 pl-9 pr-3 rounded-xl",
                    "bg-bg-tertiary border border-[rgba(255,240,220,0.06)]",
                    "text-sm text-text-primary placeholder:text-text-tertiary",
                    "focus:outline-none focus:border-accent/40",
                  )}
                />
              </div>
            </div>

            {/* List */}
            <div className="max-h-72 overflow-y-auto p-1">
              {filtered.length === 0 && (
                <div className="py-8 text-center text-xs text-text-tertiary">
                  没有匹配的币种
                </div>
              )}
              {filtered.map((s) => {
                const m = meta[s];
                const active = s === symbol;
                return (
                  <button
                    key={s}
                    onClick={() => {
                      onSymbolChange(s);
                      setOpen(false);
                      setSearch("");
                    }}
                    className={cn(
                      "w-full flex items-center justify-between gap-3 h-11 px-3 rounded-xl",
                      "transition-colors text-left",
                      active ? "bg-accent/10" : "hover:bg-bg-tertiary",
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-semibold text-text-primary">{s}</span>
                    </div>
                    {m && (
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-text-secondary tabular-nums">
                          {m.price > 0 ? m.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
                        </span>
                        <span
                          className={cn(
                            "inline-flex items-center gap-0.5 text-[11px] font-medium tabular-nums",
                            m.change24h >= 0 ? "text-bull" : "text-bear",
                          )}
                        >
                          {m.change24h >= 0 ? (
                            <TrendingUp className="w-2.5 h-2.5" />
                          ) : (
                            <TrendingDown className="w-2.5 h-2.5" />
                          )}
                          {m.change24h >= 0 ? "+" : ""}
                          {m.change24h.toFixed(2)}%
                        </span>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Timeframe pills — optional (only render if parent provides callback) */}
      {onTimeframeChange && (
        <div className="flex items-center gap-1 p-1 rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.06)]">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => onTimeframeChange(tf)}
              data-testid={`tf-${tf}`}
              className={cn(
                "h-8 px-3 text-xs font-medium rounded-full transition-all duration-150",
                "active:scale-[0.95]",
                timeframe === tf
                  ? "bg-accent text-[#140c0c] shadow-[0_0_0_1px_rgba(204,255,0,0.3)]"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary",
              )}
            >
              {t(`timeframes.${tf}`)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
