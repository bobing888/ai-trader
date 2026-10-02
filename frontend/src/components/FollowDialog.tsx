/**
 * FollowDialog — 跟单创建对话框
 *
 * 表单: pair(预填)/timeframe(预填)/direction(预填)/entry/SL/target/leverage/stake
 *
 * D1 upgrade: 从 recommendation payload 预填 ATR-based 3-tier entry levels
 *             + SL / TP1 / TP2 (显示，不一定填入表单)
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { X, Loader2, ArrowUpDown, Shield, Target, Wallet, Zap, TrendingUpDown } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createFollow } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface EntryLevel {
  price: number;
  size_pct: number;
  label: string;
}

export interface FollowDialogProps {
  isOpen: boolean;
  onClose: () => void;
  pair: string;
  timeframe: string;
  direction: "long" | "short";
  recommendedLeverage?: number;
  recommendationId?: number;
  /** D1: ATR-based entry levels from recommendation payload */
  entryLevels?: EntryLevel[];
  stopLossPrice?: number | null;
  takeProfit1Price?: number | null;
  takeProfit2Price?: number | null;
  atr?: number | null;
  riskRewardRatio?: number | null;
  quality?: "high" | "medium" | "low" | "reject" | null;
  trailingStopEnabled?: boolean;
  partialTpEnabled?: boolean;
  onSuccess?: () => void;
}

const QUALITY_BADGE = {
  high: { label: "高质", tone: "bull" as const },
  medium: { label: "中质", tone: "warning" as const },
  low: { label: "低质", tone: "bear" as const },
  reject: { label: "拒绝", tone: "bear" as const },
};

export function FollowDialog(props: FollowDialogProps) {
  const { t } = useTranslation();
  const {
    isOpen,
    onClose,
    pair,
    timeframe,
    direction,
    recommendedLeverage = 1,
    recommendationId,
    entryLevels = [],
    stopLossPrice,
    takeProfit1Price,
    takeProfit2Price,
    atr,
    riskRewardRatio,
    quality,
    trailingStopEnabled = true,
    partialTpEnabled = true,
    onSuccess,
  } = props;

  const [entryPrice, setEntryPrice] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [target, setTarget] = useState("");
  const [leverage, setLeverage] = useState(recommendedLeverage);
  const [stakeAmount, setStakeAmount] = useState("100");

  // Pre-fill D1 levels when dialog opens with a recommendation
  useEffect(() => {
    if (isOpen) {
      setLeverage(recommendedLeverage);
      // Pre-fill from recommendation levels if available
      if (entryLevels.length > 0) {
        // Use T1 (first entry level) as entry price suggestion
        setEntryPrice(entryLevels[0].price.toFixed(2));
      } else {
        setEntryPrice("");
      }
      if (stopLossPrice != null) setStopLoss(stopLossPrice.toFixed(2));
      else setStopLoss("");
      if (takeProfit1Price != null) setTarget(takeProfit1Price.toFixed(2));
      else setTarget("");
      setStakeAmount("100");
    }
  }, [isOpen, recommendedLeverage, entryLevels, stopLossPrice, takeProfit1Price]);

  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      createFollow({
        pair,
        timeframe,
        direction,
        entry_price: entryPrice ? Number(entryPrice) : null,
        stop_loss: stopLoss ? Number(stopLoss) : null,
        target: target ? Number(target) : null,
        leverage,
        stake_amount: Number(stakeAmount),
        source: "ai_recommendation",
        recommendation_id: recommendationId ?? null,
        // D3
        trailing_stop_enabled: trailingStopEnabled,
        partial_tp_enabled: partialTpEnabled,
        take_profit_1_price: takeProfit1Price ?? null,
        take_profit_2_price: takeProfit2Price ?? null,
        entry_atr: atr ?? null,
        remaining_size_pct: 1.0,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["follows"] });
      onSuccess?.();
      onClose();
    },
  });

  if (!isOpen) return null;

  const qualityCfg = quality ? QUALITY_BADGE[quality] : null;
  const showD1 = atr != null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur"
      data-testid="follow-dialog"
      onClick={onClose}
    >
      <div
        className="bg-bg-primary rounded-lg p-6 w-[480px] max-w-[92vw] shadow-2xl space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ArrowUpDown className="w-5 h-5" />
            {t("follow.dialog.title", "跟单")}
          </h2>
          <button onClick={onClose} aria-label="close">
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* D1: recommendation metadata */}
        {showD1 && (
          <div className="bg-slate-800/60 rounded p-2 space-y-1">
            <div className="flex items-center gap-2 text-xs text-slate-300">
              <Zap className="w-3 h-3 text-yellow-400" />
              <span className="font-mono">ATR = {atr!.toFixed(4)}</span>
              {riskRewardRatio != null && (
                <span className="font-mono">R:R = {riskRewardRatio.toFixed(2)}</span>
              )}
              {qualityCfg && (
                <span
                  className={cn(
                    "px-1.5 py-0.5 rounded text-[10px] font-bold",
                    qualityCfg.tone === "bull" && "bg-emerald-900 text-emerald-400",
                    qualityCfg.tone === "warning" && "bg-yellow-900 text-yellow-400",
                    qualityCfg.tone === "bear" && "bg-rose-900 text-rose-400",
                  )}
                >
                  {qualityCfg.label}
                </span>
              )}
              {trailingStopEnabled && (
                <span className="flex items-center gap-0.5 text-yellow-400">
                  <TrendingUpDown className="w-3 h-3" />
                  移动止损
                </span>
              )}
              {partialTpEnabled && (
                <span className="text-cyan-400">分批止盈</span>
              )}
            </div>

            {/* 3-tier entry levels */}
            {entryLevels.length > 0 && (
              <div className="grid grid-cols-3 gap-1 text-xs">
                {entryLevels.map((lv) => (
                  <div
                    key={lv.label}
                    className="bg-slate-700/50 rounded p-1.5 text-center"
                  >
                    <div className="text-slate-400 text-[10px]">
                      {lv.label}{" "}
                      <span className="text-slate-500">{Math.round(lv.size_pct * 100)}%</span>
                    </div>
                    <div className="font-mono text-slate-200">{lv.price.toFixed(2)}</div>
                  </div>
                ))}
              </div>
            )}

            {/* SL / TP */}
            <div className="grid grid-cols-3 gap-1 text-xs">
              <div className="text-rose-400">
                <Shield className="w-3 h-3 inline mr-0.5" />
                SL: {stopLossPrice?.toFixed(2) ?? "—"}
              </div>
              <div className="text-emerald-400">
                <Target className="w-3 h-3 inline mr-0.5" />
                TP1: {takeProfit1Price?.toFixed(2) ?? "—"}
              </div>
              <div className="text-emerald-400">
                TP2: {takeProfit2Price?.toFixed(2) ?? "—"}
              </div>
            </div>
          </div>
        )}

        {/* 预填 readonly 字段 */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-bg-secondary rounded p-2">
            <div className="text-text-tertiary">Pair</div>
            <div className="font-mono font-semibold">{pair}</div>
          </div>
          <div className="bg-bg-secondary rounded p-2">
            <div className="text-text-tertiary">TF</div>
            <div className="font-mono font-semibold">{timeframe}</div>
          </div>
          <div className="bg-bg-secondary rounded p-2">
            <div className="text-text-tertiary">Direction</div>
            <div
              className={cn(
                "font-mono font-semibold",
                direction === "long" ? "text-bull" : "text-bear",
              )}
            >
              {direction}
            </div>
          </div>
        </div>

        {/* 可编辑字段 */}
        <Field
          icon={<Wallet className="w-4 h-4" />}
          label="Entry Price"
          value={entryPrice}
          onChange={setEntryPrice}
          placeholder={entryLevels.length > 0 ? "T1 价格 (已预填)" : "现价 (可选)"}
          testid="follow-entry"
        />
        <Field
          icon={<Shield className="w-4 h-4 text-bear" />}
          label="Stop Loss"
          value={stopLoss}
          onChange={setStopLoss}
          placeholder={stopLossPrice != null ? `${stopLossPrice.toFixed(2)} (已预填)` : "止损 (可选)"}
          testid="follow-sl"
        />
        <Field
          icon={<Target className="w-4 h-4 text-bull" />}
          label="Target (TP1)"
          value={target}
          onChange={setTarget}
          placeholder={takeProfit1Price != null ? `${takeProfit1Price.toFixed(2)} (已预填)` : "止盈 (可选)"}
          testid="follow-target"
        />

        <div className="grid grid-cols-2 gap-3">
          <NumberField
            label="Leverage"
            value={leverage}
            onChange={setLeverage}
            min={1}
            max={125}
            testid="follow-leverage"
          />
          <NumberField
            label="Stake (USDT)"
            value={Number(stakeAmount)}
            onChange={(v) => setStakeAmount(String(v))}
            min={1}
            max={1_000_000}
            testid="follow-stake"
            decimals
          />
        </div>

        {mutation.error && (
          <div className="text-xs text-bear" data-testid="follow-error">
            {(mutation.error as Error).message || "跟单失败"}
          </div>
        )}

        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          data-testid="follow-submit"
          className="w-full py-2 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
          {t("follow.dialog.submit", "确认跟单")}
        </button>
      </div>
    </div>
  );
}

function Field(props: {
  icon: React.ReactNode;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  testid?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="text-text-secondary flex items-center gap-1 mb-1">
        {props.icon}
        {props.label}
      </span>
      <input
        type="text"
        inputMode="decimal"
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        data-testid={props.testid}
        className="w-full bg-bg-secondary border border-[rgba(255,240,220,0.08)] rounded px-3 py-2 font-mono focus:border-emerald-500 outline-none"
      />
    </label>
  );
}

function NumberField(props: {
  label: string;
  value: number | string;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  testid?: string;
  decimals?: boolean;
}) {
  return (
    <label className="block text-sm">
      <span className="text-text-secondary mb-1 block">{props.label}</span>
      <input
        type="number"
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
        min={props.min}
        max={props.max}
        step={props.decimals ? 0.01 : 1}
        data-testid={props.testid}
        className="w-full bg-bg-secondary border border-[rgba(255,240,220,0.08)] rounded px-3 py-2 font-mono focus:border-emerald-500 outline-none"
      />
    </label>
  );
}
