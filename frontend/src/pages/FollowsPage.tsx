/**
 * FollowsPage — 跟单记录页 (B-Follow Step 2)
 *
 * 3 tabs: open | closed | cancelled
 * 每条 follow 卡片显示: pair/direction/stake/entry/SL/target/PnL/状态
 */

import { useState } from "react";
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
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { cn } from "@/lib/utils";
import {
  cancelFollow,
  closeFollow,
  fetchFollows,
  type UserFollow,
} from "@/lib/api";

type Tab = "open" | "closed" | "cancelled";

export function FollowsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("open");
  const queryClient = useQueryClient();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["follows", tab],
    queryFn: () => fetchFollows({ status: tab, limit: 100 }),
    refetchInterval: 30_000,
  });

  const closeMutation = useMutation({
    mutationFn: ({ id, exit_price }: { id: number; exit_price: number }) =>
      closeFollow(id, { exit_price }),
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
          {isFetching ? <Loader className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
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
        {isLoading ? "loading…" : t("follows.count", `${items.length} 项 (${totals} 总计)`, {
          count: items.length,
          total: totals,
        })}
      </div>

      {/* Cards grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="h-40 animate-pulse">
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
              onClose={(exit_price) => closeMutation.mutate({ id: f.id, exit_price })}
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
  onClose: (exit_price: number) => void;
  onCancel: () => void;
  closing: boolean;
  cancelling: boolean;
}) {
  const { follow, onClose, onCancel, closing, cancelling } = props;
  const f = follow;

  const DirectionIcon = f.direction === "long" ? TrendingUp : TrendingDown;
  const dirTone = f.direction === "long" ? "text-emerald-400" : "text-rose-400";

  const pnl = f.pnl_pct ?? 0;
  const pnlAbs = f.pnl_abs ?? 0;
  const pnlTone = pnl > 0 ? "text-emerald-400" : pnl < 0 ? "text-rose-400" : "text-slate-400";

  const statusTone: "bull" | "bear" | "muted" =
    f.status === "open" ? "bull" : f.status === "closed" ? profitToTone(f.pnl_pct) : "muted";

  return (
    <Card className="p-4 space-y-3" data-testid={`follow-card-${f.id}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DirectionIcon className={cn("w-5 h-5", dirTone)} />
          <span className="font-semibold">{f.pair}</span>
          <Badge tone="muted">{f.timeframe}</Badge>
          {f.leverage > 1 && <Badge tone="warning">{f.leverage}×</Badge>}
        </div>
        <Badge tone={statusTone}>{f.status}</Badge>
      </div>

      {/* Price levels */}
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
            止损
          </span>
          <span className="font-mono text-rose-400">
            {f.stop_loss?.toFixed(2) ?? "—"}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-slate-500 flex items-center gap-1">
            <TargetIcon className="w-3 h-3" />
            目标
          </span>
          <span className="font-mono text-emerald-400">
            {f.target?.toFixed(2) ?? "—"}
          </span>
        </div>
      </div>

      {/* Stake + PnL */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-700">
        <div className="text-xs text-slate-400">
          本金 <span className="font-mono text-slate-200">{f.stake_amount.toFixed(2)}</span> USDT
        </div>
        {f.status !== "open" && f.pnl_pct !== null && (
          <div className={cn("text-sm font-semibold", pnlTone)} data-testid={`pnl-${f.id}`}>
            {pnl > 0 ? "+" : ""}
            {(pnl * 100).toFixed(2)}% ({pnlAbs > 0 ? "+" : ""}
            {pnlAbs.toFixed(2)} USDT)
          </div>
        )}
      </div>

      {/* Actions */}
      {f.status === "open" && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => onClose(f.entry_price ?? 0)}
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