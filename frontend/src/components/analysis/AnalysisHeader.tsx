/**
 * AnalysisHeader — 顶部当前价格 + 24h 涨跌 + 元数据。
 * 当前价用大字号 (4xl/5xl) 作为判断锚点；ticker mock 模式下降级到 K 线最新收盘。
 */

import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";
import type { SymbolMeta } from "@/lib/api";

interface Props {
  symbol: string;
  timeframe: string;
  ticker?: SymbolMeta;
  klinePrice?: number;
  asOf?: string;
}

export function AnalysisHeader({ symbol, timeframe, ticker, klinePrice, asOf }: Props) {
  const tickerAvailable = !!ticker && ticker.price > 0;
  const tickerPrice = tickerAvailable ? ticker!.price : 0;
  const price = tickerPrice > 0 ? tickerPrice : klinePrice ?? 0;
  const change24h = tickerAvailable ? ticker!.change_24h : undefined;
  const hasPrice = price > 0;

  return (
    <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] px-5 py-5 sm:px-7 sm:py-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="flex items-baseline gap-3 sm:gap-5 flex-wrap">
        <span className="text-xl sm:text-2xl font-bold text-text-primary tracking-tight">
          {symbol}
        </span>
        <Badge tone="muted" className="text-sm">{timeframe}</Badge>
        {hasPrice ? (
          <div className="flex items-baseline gap-2 sm:gap-3">
            <span className="text-4xl sm:text-5xl font-black tracking-tight text-text-primary tabular-nums">
              {price.toLocaleString(undefined, {
                maximumFractionDigits: 2,
                minimumFractionDigits: 2,
              })}
            </span>
            {typeof change24h === "number" && (
              <span
                className={cn(
                  "text-2xl sm:text-3xl font-bold tabular-nums",
                  change24h >= 0 ? "text-bull" : "text-bear",
                )}
              >
                {change24h >= 0 ? "+" : ""}
                {change24h.toFixed(2)}%
              </span>
            )}
          </div>
        ) : (
          <span className="text-2xl text-text-tertiary">—</span>
        )}
        <span className="text-sm text-text-tertiary">
          {change24h !== undefined ? "24h 涨跌" : tickerAvailable ? "实时价" : "最新 K 线收盘"}
        </span>
      </div>

      <div className="text-right space-y-0.5">
        <p className="text-[11px] text-text-tertiary uppercase tracking-wider">分析基准</p>
        <p className="text-sm text-text-secondary tabular-nums">
          {asOf
            ? new Date(asOf).toLocaleString("zh-CN", { hour12: false })
            : new Date().toLocaleTimeString("zh-CN", { hour12: false })}
        </p>
        <p className="text-[10px] text-text-tertiary">
          价格 / 后端分析 · 5s / 60s 刷新
        </p>
      </div>
    </div>
  );
}
