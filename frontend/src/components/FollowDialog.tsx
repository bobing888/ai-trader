/**
 * FollowDialog — 跟单创建对话框
 *
 * 表单: pair(预填)/timeframe(预填)/direction(预填)/entry/SL/target/leverage/stake
 * 提交 → POST /api/follows
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { X, Loader2, ArrowUpDown, Shield, Target, Wallet } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createFollow } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface FollowDialogProps {
  isOpen: boolean;
  onClose: () => void;
  pair: string;
  timeframe: string;
  direction: "long" | "short";
  recommendedLeverage?: number;
  recommendationId?: number;
  onSuccess?: () => void;
}

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
    onSuccess,
  } = props;

  const [entryPrice, setEntryPrice] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [target, setTarget] = useState("");
  const [leverage, setLeverage] = useState(recommendedLeverage);
  const [stakeAmount, setStakeAmount] = useState("100");

  useEffect(() => {
    if (isOpen) {
      setLeverage(recommendedLeverage);
      setEntryPrice("");
      setStopLoss("");
      setTarget("");
      setStakeAmount("100");
    }
  }, [isOpen, recommendedLeverage]);

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
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["follows"] });
      onSuccess?.();
      onClose();
    },
  });

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur"
      data-testid="follow-dialog"
      onClick={onClose}
    >
      <div
        className="bg-bg-primary rounded-lg p-6 w-[420px] max-w-[92vw] shadow-2xl space-y-4"
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
          placeholder="现价 (可选)"
          testid="follow-entry"
        />
        <Field
          icon={<Shield className="w-4 h-4 text-bear" />}
          label="Stop Loss"
          value={stopLoss}
          onChange={setStopLoss}
          placeholder="止损 (可选)"
          testid="follow-sl"
        />
        <Field
          icon={<Target className="w-4 h-4 text-bull" />}
          label="Target"
          value={target}
          onChange={setTarget}
          placeholder="止盈 (可选)"
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
            max={1000000}
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