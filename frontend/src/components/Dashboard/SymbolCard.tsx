/**
 * SymbolCard — Dashboard 单币种卡
 *
 * 三种渲染态：
 * 1. 有信号：direction/quality/置信度/TP/SL/R:R
 * 2. 无信号：灰色卡，"观望"
 * 3. 降级：黄色边框 + ⚠️ + error
 *
 * 视觉借鉴：
 * - lauramyol13/crypto-signal-dashboard (MIT) signalConfig 三色 map
 * - marketcalls/trading-dashboard (MIT) 红绿配色
 */

import { ArrowDownRight, ArrowUpRight, Eye, AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import type { OverviewItem } from "@/lib/dashboardApi";

export interface SymbolCardProps {
  item: OverviewItem;
  onJump?: (symbol: string) => void;
}

const QUALITY_STYLE: Record<string, string> = {
  high: "border-bull/40 bg-bull/5",
  medium: "border-accent/30 bg-accent/5",
  low: "border-text-tertiary/30 bg-bg-tertiary",
  reject: "border-bear/30 bg-bear/5",
};

const QUALITY_LABEL: Record<string, string> = {
  high: "高质量",
  medium: "中等",
  low: "低质",
  reject: "不建议",
};

function fmtPrice(p: number): string {
  if (p >= 1000) return p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (p >= 1) return p.toFixed(2);
  if (p >= 0.01) return p.toFixed(4);
  return p.toFixed(6);
}

function fmtPct(p: number): string {
  const sign = p > 0 ? "+" : "";
  return `${sign}${p.toFixed(2)}%`;
}

export function SymbolCard({ item, onJump }: SymbolCardProps) {
  const { symbol, price, change_24h_pct, signal, degraded, error } = item;

  // 降级态
  if (degraded) {
    return (
      <button
        type="button"
        onClick={() => onJump?.(symbol)}
        data-testid="symbol-card-degraded"
        data-symbol={symbol}
        className="text-left rounded-2xl border border-yellow-500/40 bg-yellow-500/5 p-4 hover:border-yellow-500/60 transition-colors w-full"
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-text-primary">{symbol.replace("-USDT", "")}</span>
          <AlertTriangle className="w-4 h-4 text-yellow-500" />
        </div>
        <p className="text-xs text-yellow-500/90 leading-relaxed line-clamp-2">
          拉取失败：{error ?? "未知错误"}
        </p>
      </button>
    );
  }

  // 无信号
  if (!signal) {
    const changePositive = change_24h_pct > 0;
    return (
      <button
        type="button"
        onClick={() => onJump?.(symbol)}
        data-testid="symbol-card-no-signal"
        data-symbol={symbol}
        className="text-left rounded-2xl border border-[rgba(255,240,220,0.06)] bg-bg-secondary p-4 hover:border-[rgba(255,240,220,0.12)] transition-colors w-full"
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-text-primary">{symbol.replace("-USDT", "")}</span>
          <span className={cn("text-xs font-medium tabular-nums", changePositive ? "text-bull" : "text-bear")}>
            {fmtPct(change_24h_pct)}
          </span>
        </div>
        <div className="text-lg font-mono font-bold text-text-primary tabular-nums">
          {price > 0 ? `$${fmtPrice(price)}` : "—"}
        </div>
        <div className="flex items-center gap-1.5 mt-2 text-xs text-text-tertiary">
          <Eye className="w-3 h-3" />
          观望
        </div>
      </button>
    );
  }

  // 有信号
  const isLong = signal.direction === "long";
  const directionColor = isLong ? "text-bull" : "text-bear";
  const directionBg = isLong ? "bg-bull/10 border-bull/30" : "bg-bear/10 border-bear/30";
  const qualityClass = QUALITY_STYLE[signal.quality] ?? QUALITY_STYLE.medium;

  return (
    <button
      type="button"
      onClick={() => onJump?.(symbol)}
      data-testid="symbol-card-with-signal"
      data-symbol={symbol}
      className={cn(
        "text-left rounded-2xl border p-4 hover:scale-[1.01] transition-all w-full",
        qualityClass,
      )}
    >
      {/* 头部：symbol + 24h 变动 */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-text-primary">{symbol.replace("-USDT", "")}</span>
        <span className={cn("text-xs font-medium tabular-nums", change_24h_pct > 0 ? "text-bull" : "text-bear")}>
          {fmtPct(change_24h_pct)}
        </span>
      </div>

      {/* 价格 */}
      <div className="text-xl font-mono font-bold text-text-primary tabular-nums mb-3">
        ${fmtPrice(price)}
      </div>

      {/* 方向徽章 + quality 徽章 */}
      <div className="flex items-center gap-1.5 mb-2">
        <span className={cn("inline-flex items-center gap-0.5 px-2 py-0.5 rounded-md border text-xs font-semibold", directionBg, directionColor)}>
          {isLong ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {isLong ? "做多" : "做空"}
        </span>
        <span className="inline-flex px-1.5 py-0.5 rounded-md bg-bg-tertiary text-[10px] font-medium text-text-secondary">
          {QUALITY_LABEL[signal.quality] ?? signal.quality}
        </span>
        <span className="text-[10px] text-text-tertiary font-mono ml-auto">
          {signal.timeframe}
        </span>
      </div>

      {/* 置信度条 */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-[10px] text-text-tertiary mb-1">
          <span>置信度</span>
          <span className="font-mono tabular-nums">{Math.round(signal.confidence * 100)}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
          <div
            className={cn("h-full transition-all", isLong ? "bg-bull" : "bg-bear")}
            style={{ width: `${Math.min(100, Math.round(signal.confidence * 100))}%` }}
          />
        </div>
      </div>

      {/* 下一预期走势 */}
      <div className="text-xs text-text-secondary mb-2 leading-relaxed">
        {signal.next_predicted_move}
      </div>

      {/* TP / SL / R:R */}
      {(signal.take_profit_1 || signal.stop_loss) && (
        <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-[rgba(255,240,220,0.06)]">
          <div className="text-[10px]">
            <div className="text-text-tertiary">TP1</div>
            <div className="font-mono tabular-nums text-text-secondary">
              {signal.take_profit_1 ? `$${fmtPrice(signal.take_profit_1)}` : "—"}
            </div>
          </div>
          <div className="text-[10px]">
            <div className="text-text-tertiary">SL</div>
            <div className="font-mono tabular-nums text-text-secondary">
              {signal.stop_loss ? `$${fmtPrice(signal.stop_loss)}` : "—"}
            </div>
          </div>
          <div className="text-[10px]">
            <div className="text-text-tertiary">R:R</div>
            <div className="font-mono tabular-nums text-text-secondary">
              {signal.risk_reward_ratio > 0 ? signal.risk_reward_ratio.toFixed(2) : "—"}
            </div>
          </div>
        </div>
      )}
    </button>
  );
}