/**
 * FollowsPage — 跟单记录页 (B-Follow Step 2 + D6)
 *
 * 3 tabs: open | closed | cancelled
 * 每条 follow 卡片显示:
 *   - D1: 3-tier entry levels (T1/T2/T3) + ATR + R:R ratio
 *   - D1: stop_loss / take_profit_1 / take_profit_2
 *   - D2: quality badge (high/medium/low/reject)
 *   - D3: trailing SL 移动止损 + partial TP 状态
 *   - D6: 实时未实现盈亏（每 5s polling）
 */

import { useEffect, useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  TrendingUp,
  TrendingDown,
  X,
  Check,
  RefreshCw,
  Loader2 as Loader,
  Wallet,
  Clock,
  Target as TargetIcon,
  Shield,
  Zap,
  TrendingUpDown,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { cn } from "@/lib/utils";
import {
  cancelFollow,
  closeFollow,
  fetchFollows,
  fetchSymbolMeta,
  type UserFollow,
} from "@/lib/api";

// ─── Unrealized PnL ─────────────────────────────────────────────────────────

function useUnrealizedPnl(follows: UserFollow[]) {
  const [prices, setPrices] = useState<Record<string, number>>({});

  useEffect(() => {
    const open = follows.filter((f) => f.status === "open");
    if (!open.length) return;
    const pairs = [...new Set(open.map((f) => f.pair))];
    Promise.all(pairs.map((p) => fetchSymbolMeta(p)))
      .then((metas) => {
        const map: Record<string, number> = {};
        metas.forEach((m) => { map[m.symbol] = m.price; });
        setPrices(map);
      })
      .catch(() => {/* silent */});
  }, [follows]);

  const computeUnrealized = (f: UserFollow): { pnl_pct: number; pnl_abs: number } | null => {
    if (f.status !== "open" || f.entry_price == null) return null;
    const price = prices[f.pair];
    if (!price) return null;
    const sign = f.direction === "long" ? 1 : -1;
    const pnl_pct = sign * (price - f.entry_price) / f.entry_price * f.leverage;
    const pnl_abs = f.stake_amount * pnl_pct;
    return { pnl_pct, pnl_abs };
  };

  return { prices, computeUnrealized };
}

// ─── Quality badge ────────────────────────────────────────────────────────────

const QUALITY_CONFIG = {
  high: { tone: "bull" as const, label: "高质", color: "text-emerald-400" },
  medium: { tone: "warning" as const, label: "中质", color: "text-yellow-400" },
  low: { tone: "bear" as const, label: "低质", color: "text-rose-400" },
  reject: { tone: "bear" as const, label: "拒绝", color: "text-rose-500" },
};

// ─── Main ────────────────────────────────────────────────────────────────────

type Tab = "open" | "closed" | "cancelled";

export function FollowsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("open");
  const queryClient = useQueryClient();

  // D6: open tab polls every 5s for real-time PnL; others 30s
  const refetchInterval = tab === "open" ? 5_000 : 30_000;

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["follows", tab],
    queryFn: () => fetchFollows({ status: tab, limit: 100 }),
    refetchInterval,
  });

  const { computeUnrealized } = useUnrealizedPnl(data?.items ?? []);

  const closeMutation = useMutation({
    mutationFn: ({
      id,
      exit_price,
      exit_size_pct = 1.0,
    }: {
      id: number;
      exit_price: number;
      exit_size_pct?: number;
    }) => closeFollow(id, { exit_price, exit_size_pct }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["follows"] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: ({ id }: { id: number }) => cancelFollow(id, { reason: "manual" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["follows"] });
    },
  });

  const items = data?.items ?? [];
  const totals = data?.total ?? 0;

  return (
    <div className="space-y-6 p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("follows.title", "跟单")}</h1>
        <button
          onClick={() => refetch()}
          className="p-2 rounded hover:bg-slate-700/30"
          aria-label="refresh"
        >
          {isFetching ? (
            <Loader className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
        </button>
      </header>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-700">
        {(["open", "closed", "cancelled"] as Tab[]).map((t_) => (
          <button
            key={t_}
            onClick={() => setTab(t_)}
            data-testid={`follows-tab-${t_}`}
            className={cn(
              "px-4 py-2 text-sm border-b-2 -mb-px transition-colors",
              tab === t_
                ? "border-emerald-400 text-emerald-400"
                : "border-transparent text-slate-400 hover:text-slate-200",
            )}
          >
            {t(`follows.tab.${t_}`, t_)}
          </button>
        ))}
      </div>

      {/* Summary */}
      <div className="text-sm text-slate-400">
        {isLoading
          ? "loading…"
          : t("follows.count", `${items.length} 项 (${totals} 总计)`, {
              count: items.length,
              total: totals,
            })}
      </div>

      {/* Cards grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="h-48 animate-pulse">
              <span className="sr-only">loading</span>
            </Card>
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Wallet className="w-12 h-12" />}
          title={t("follows.empty.title", "暂无跟单")}
          description={t("follows.empty.desc", "去推荐页选中一条点击「跟单」即可")}
        />
      ) : (
        <div
          data-testid="follows-list"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {items.map((f) => (
            <FollowCard
              key={f.id}
              follow={f}
              unrealized={computeUnrealized(f)}
              onClose={(exit_price, exit_size_pct) =>
                closeMutation.mutate({ id: f.id, exit_price, exit_size_pct })
              }
              onCancel={() => cancelMutation.mutate({ id: f.id })}
              closing={closeMutation.isPending}
              cancelling={cancelMutation.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Card ────────────────────────────────────────────────────────────────────

function FollowCard(props: {
  follow: UserFollow;
  unrealized: { pnl_pct: number; pnl_abs: number } | null;
  onClose: (exit_price: number, exit_size_pct?: number) => void;
  onCancel: () => void;
  closing: boolean;
  cancelling: boolean;
}) {
  const { follow: f, unrealized, onClose, onCancel, closing, cancelling } = props;
  const DirectionIcon = f.direction === "long" ? TrendingUp : TrendingDown;
  const dirTone = f.direction === "long" ? "text-emerald-400" : "text-rose-400";

  // Closed realized PnL
  const realizedPnl = f.pnl_pct ?? 0;
  const realizedAbs = f.pnl_abs ?? 0;
  const realizedTone = realizedPnl > 0 ? "text-emerald-400" : realizedPnl < 0 ? "text-rose-400" : "text-slate-400";

  // D6: unrealized
  const unrealPct = unrealized?.pnl_pct ?? 0;
  const unrealAbs = unrealized?.pnl_abs ?? 0;
  const unrealTone =
    f.status === "open"
      ? unrealPct > 0
        ? "text-emerald-400"
        : unrealPct < 0
        ? "text-rose-400"
        : "text-slate-400"
      : realizedTone;

  // D3: trailing vs original SL
  const hasTrailing = f.trailing_stop_enabled && f.current_stop_loss != null;
  const slMoved = hasTrailing && f.current_stop_loss !== f.stop_loss;
  const origSL = f.stop_loss;
  const currSL = f.current_stop_loss;

  // D3: partial TP status
  const partialTaken = f.partial_tp_taken === 1;
  const remainingSize = f.remaining_size_pct ?? 1.0;

  const statusTone: "bull" | "bear" | "muted" =
    f.status === "open"
      ? unrealPct > 0
        ? "bull"
        : unrealPct < 0
        ? "bear"
        : "muted"
      : f.status === "closed"
      ? profitToTone(f.pnl_pct)
      : "muted";

  return (
    <Card className="p-4 space-y-3" data-testid={`follow-card-${f.id}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DirectionIcon className={cn("w-5 h-5", dirTone)} />
          <span className="font-semibold">{f.pair}</span>
          <Badge tone="muted">{f.timeframe}</Badge>
          {f.leverage > 1 && <Badge tone="warning">{f.leverage}×</Badge>}
          {/* D2: quality badge */}
          {f.source === "ai_recommendation" && (
            <Badge tone={QUALITY_CONFIG.medium.tone}>
              {QUALITY_CONFIG.medium.label}
            </Badge>
          )}
        </div>
        <Badge tone={statusTone}>{f.status}</Badge>
      </div>

      {/* D1: 3-tier entry levels — show if available */}
      {f.source === "ai_recommendation" && f.entry_atr != null && (
        <div className="bg-slate-800/50 rounded p-2 text-xs space-y-1">
          <div className="flex items-center gap-1 text-slate-400">
            <Zap className="w-3 h-3" />
            ATR <span className="text-slate-200 font-mono">{f.entry_atr.toFixed(4)}</span>
            {f.trailing_stop_enabled === true && (
              <span className="ml-1 text-yellow-400 flex items-center gap-0.5">
                <TrendingUpDown className="w-3 h-3" />
                移动止损
              </span>
            )}
            {f.partial_tp_enabled === true && (
              <span className="ml-1 text-cyan-400">分批止盈</span>
            )}
          </div>
        </div>
      )}

      {/* D1: Price levels */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="flex flex-col">
          <span className="text-slate-500 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            入场
          </span>
          <span className="font-mono">{f.entry_price?.toFixed(2) ?? "—"}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-slate-500 flex items-center gap-1">
            <Shield className="w-3 h-3" />
            {slMoved ? "移动止损" : "止损"}
          </span>
          <span
            className={cn(
              "font-mono",
              slMoved && f.direction === "long" ? "text-yellow-400" : "text-rose-400",
            )}
          >
            {currSL != null ? currSL.toFixed(2) : f.stop_loss?.toFixed(2) ?? "—"}
            {slMoved && origSL != null && currSL != null && (
              <span className="text-slate-500 text-[10px] ml-0.5">
                ({f.direction === "long" ? "↓" : "↑"}
                {Math.abs(currSL - origSL).toFixed(2)})
              </span>
            )}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-slate-500 flex items-center gap-1">
            <TargetIcon className="w-3 h-3" />
            TP1
          </span>
          <span className="font-mono text-emerald-400">
            {f.take_profit_1_price?.toFixed(2) ?? f.target?.toFixed(2) ?? "—"}
          </span>
        </div>
      </div>

      {/* D1: TP2 + ATR */}
      {f.take_profit_2_price != null && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex flex-col">
            <span className="text-slate-500 flex items-center gap-1">
              <TargetIcon className="w-3 h-3" />
              TP2 (尾部)
            </span>
            <span className="font-mono text-emerald-400">
              {f.take_profit_2_price.toFixed(2)}
            </span>
          </div>
          {f.entry_atr != null && (
            <div className="flex flex-col">
              <span className="text-slate-500">R:R</span>
              <span className="font-mono text-slate-200">
                {f.risk_reward_ratio?.toFixed(2) ?? "—"}
              </span>
            </div>
          )}
        </div>
      )}

      {/* D3: partial TP status */}
      {f.status === "open" && f.partial_tp_enabled === true && (
        <div className="text-xs text-cyan-400">
          {partialTaken ? (
            <span>✓ TP1 已触发，剩余 {Math.round(remainingSize * 100)}% 仓位</span>
          ) : (
            <span>分批止盈：TP1 触发后平 50%</span>
          )}
        </div>
      )}

      {/* Stake + PnL */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-700">
        <div className="text-xs text-slate-400">
          本金 <span className="font-mono text-slate-200">{f.stake_amount.toFixed(2)}</span>{" "}
          USDT
          {f.status === "open" && remainingSize < 1.0 && (
            <span className="ml-1 text-cyan-400">
              (剩 {Math.round(remainingSize * 100)}%)
            </span>
          )}
        </div>
        {f.status === "open" && unrealized ? (
          <div
            className={cn("text-sm font-semibold", unrealTone)}
            data-testid={`unreal-pnl-${f.id}`}
          >
            {unrealPct > 0 ? "+" : ""}
            {(unrealPct * 100).toFixed(2)}% ({unrealAbs > 0 ? "+" : ""}
            {unrealAbs.toFixed(2)} USDT)
          </div>
        ) : f.status !== "open" && f.pnl_pct !== null ? (
          <div
            className={cn("text-sm font-semibold", realizedTone)}
            data-testid={`pnl-${f.id}`}
          >
            {realizedPnl > 0 ? "+" : ""}
            {(realizedPnl * 100).toFixed(2)}% ({realizedAbs > 0 ? "+" : ""}
            {realizedAbs.toFixed(2)} USDT)
          </div>
        ) : null}
      </div>

      {/* Actions */}
      {f.status === "open" && (
        <div className="flex gap-2 pt-1">
          {/* D3: partial TP close */}
          {f.partial_tp_enabled === true &&
            f.partial_tp_taken === 0 &&
            f.take_profit_1_price != null && (
              <button
                onClick={() => onClose(f.take_profit_1_price!, 0.5)}
                disabled={closing}
                data-testid={`partial-close-${f.id}`}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-xs"
              >
                TP1 半平
              </button>
            )}
          <button
            onClick={() => onClose(f.entry_price ?? 0, 1.0)}
            disabled={closing}
            data-testid={`close-${f.id}`}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-xs"
          >
            <Check className="w-3 h-3" /> 出场
          </button>
          <button
            onClick={onCancel}
            disabled={cancelling}
            data-testid={`cancel-${f.id}`}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-xs"
          >
            <X className="w-3 h-3" /> 撤销
          </button>
        </div>
      )}
    </Card>
  );
}

function profitToTone(pnl: number | null): "bull" | "bear" | "muted" {
  if (pnl === null) return "muted";
  return pnl > 0 ? "bull" : pnl < 0 ? "bear" : "muted";
}
