/**
 * TrendAnalysisPanel — 简化版趋势分析。
 *
 * 重构动机：旧版展示太多指标细节（雷达图、指标共振条、支撑/压力位网格），
 * 用户诉求是「只要结论 + 几条主要理由，方便据此操作」。
 *
 * 现在只输出：
 *   1. 顶部综合判读（大字、彩色）
 *   2. 一句话定性
 *   3. 主要理由（按重要度排序，最多 5 条，文字 + 大字号）
 *   4. 操作建议（做多/做空/止损）
 *   5. 可折叠的"原始指标"折叠区（想要细节的人自己展开）
 */

import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  Minus,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import {
  adx,
  atr,
  ema,
  macd,
  obv,
  rsi,
  sma,
} from "@/lib/indicators";
import { Card, CardBody } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

export interface TrendAnalysisPanelProps {
  candles: Array<{ time: number; open: number; high: number; low: number; close: number; volume: number }>;
  symbol: string;
  timeframe: string;
  /** Current price & 24h change for context (operational reference) */
  currentPrice?: number;
  change24hPct?: number;
}

type Verdict = "strong_bull" | "bull" | "neutral" | "bear" | "strong_bear" | "choppy" | "crisis";

interface VerdictStyle {
  label: string;
  shortLabel: string;
  color: string;
  bg: string;
  ring: string;
  icon: typeof TrendingUp;
  description: string;
  actionLabel: string;
  actionTone: "bull" | "bear" | "neutral";
}

const VERDICT_STYLES: Record<Verdict, VerdictStyle> = {
  strong_bull: {
    label: "强烈做多",
    shortLabel: "强势多头",
    color: "text-bull",
    bg: "bg-bull/10",
    ring: "ring-bull/40",
    icon: TrendingUp,
    description: "多指标共振向上，趋势强劲，可顺势做多。",
    actionLabel: "做多为主",
    actionTone: "bull",
  },
  bull: {
    label: "偏多做多",
    shortLabel: "偏多震荡",
    color: "text-bull/90",
    bg: "bg-bull/5",
    ring: "ring-bull/30",
    icon: ArrowUpRight,
    description: "多头占优但动能减弱，关注回调企稳做多。",
    actionLabel: "回调做多",
    actionTone: "bull",
  },
  neutral: {
    label: "暂不操作",
    shortLabel: "中性盘整",
    color: "text-text-secondary",
    bg: "bg-bg-tertiary",
    ring: "ring-border-subtle",
    icon: Minus,
    description: "多空力量均衡，建议观望等待方向突破。",
    actionLabel: "观望",
    actionTone: "neutral",
  },
  choppy: {
    label: "高抛低吸",
    shortLabel: "震荡洗盘",
    color: "text-warning",
    bg: "bg-warning/10",
    ring: "ring-warning/30",
    icon: Activity,
    description: "价格在区间内反复，建议高抛低吸，止损严格。",
    actionLabel: "区间操作",
    actionTone: "neutral",
  },
  bear: {
    label: "偏空做空",
    shortLabel: "偏空回落",
    color: "text-bear/90",
    bg: "bg-bear/5",
    ring: "ring-bear/30",
    icon: ArrowDownRight,
    description: "空头占优，反弹做空优于抄底。",
    actionLabel: "反弹做空",
    actionTone: "bear",
  },
  strong_bear: {
    label: "强烈做空",
    shortLabel: "强势空头",
    color: "text-bear",
    bg: "bg-bear/10",
    ring: "ring-bear/40",
    icon: TrendingDown,
    description: "多指标共振向下，趋势强劲，可顺势做空。",
    actionLabel: "做空为主",
    actionTone: "bear",
  },
  crisis: {
    label: "减仓观望",
    shortLabel: "高风险 / 危机",
    color: "text-danger",
    bg: "bg-danger/10",
    ring: "ring-danger/40",
    icon: AlertTriangle,
    description: "波动率急剧上升，流动性变差，建议减仓或观望。",
    actionLabel: "减仓离场",
    actionTone: "bear",
  },
};

interface Reason {
  stance: 1 | 0 | -1;
  text: string;
  detail: string;
}

interface Analysis {
  verdict: Verdict;
  score: number;
  headline: string;
  reasons: Reason[];
  sr: { price: number; r1: number; r2: number; s1: number; s2: number };
  actions: { label: string; value: string; tone: "bull" | "bear" | "neutral" }[];
  raw: {
    ma20: number;
    ma60: number;
    ema12: number;
    ema26: number;
    macd: number;
    rsi: number;
    adx: number;
    pdi: number;
    ndi: number;
    atr: number;
    atrPct: number;
    volTrend: number;
    ma20Bias: number;
  };
}

export function TrendAnalysisPanel({
  candles,
  symbol,
  timeframe,
  currentPrice,
  change24hPct,
}: TrendAnalysisPanelProps) {
  const analysis = useMemo(() => analyze(candles, timeframe), [candles, timeframe]);
  const [showRaw, setShowRaw] = useState(false);

  if (!analysis) {
    return null;
  }

  const style = VERDICT_STYLES[analysis.verdict];
  const Icon = style.icon;
  const price = currentPrice ?? analysis.sr.price;

  return (
    <Card>
      <CardBody className="space-y-5 p-6 sm:p-8">
        <div className="flex flex-wrap items-end justify-between gap-3 pb-4 border-b border-border-subtle">
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="text-2xl sm:text-3xl font-black tracking-tight text-text-primary tabular-nums">
              {price.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}
            </span>
            {typeof change24hPct === "number" && (
              <span
                className={cn(
                  "text-lg sm:text-xl font-bold tabular-nums",
                  change24hPct >= 0 ? "text-bull" : "text-bear",
                )}
              >
                {change24hPct >= 0 ? "+" : ""}
                {change24hPct.toFixed(2)}%
              </span>
            )}
            <span className="text-base text-text-tertiary font-medium">
              {symbol} · {timeframe}
            </span>
          </div>
          <p className="text-[11px] text-text-tertiary tabular-nums">
            基于最近 100 根 K 线 · 实时计算
          </p>
        </div>

        <div
          className={cn(
            "rounded-2xl border px-6 py-7 sm:px-8 sm:py-10 flex flex-col items-center text-center gap-3",
            style.bg,
            "border-current/20",
          )}
        >
          <div className={cn("w-16 h-16 rounded-2xl flex items-center justify-center ring-2", style.bg, style.ring)}>
            <Icon className={cn("w-9 h-9", style.color)} />
          </div>
          <p className={cn("text-5xl sm:text-6xl font-black tracking-tight leading-none", style.color)}>
            {style.label}
          </p>
          <p className="text-xl sm:text-2xl font-semibold text-text-primary max-w-2xl leading-snug">
            {analysis.headline}
          </p>
          <p className="text-sm sm:text-base text-text-secondary max-w-xl leading-relaxed">
            {style.description}
          </p>
        </div>

        <section>
          <p className="text-xs sm:text-sm uppercase tracking-widest text-text-tertiary font-semibold mb-3">
            主要理由
          </p>
          <ul className="space-y-2.5">
            {analysis.reasons.slice(0, 5).map((r, i) => (
              <li
                key={i}
                className={cn(
                  "flex items-start gap-3 rounded-xl px-4 py-3 text-lg sm:text-xl font-medium leading-snug",
                  r.stance > 0 && "bg-bull/8 text-bull",
                  r.stance < 0 && "bg-bear/8 text-bear",
                  r.stance === 0 && "bg-bg-tertiary text-text-secondary",
                )}
              >
                <span
                  className={cn(
                    "shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold tabular-nums mt-1",
                    r.stance > 0 && "bg-bull/20 text-bull",
                    r.stance < 0 && "bg-bear/20 text-bear",
                    r.stance === 0 && "bg-bg-secondary text-text-tertiary",
                  )}
                >
                  {i + 1}
                </span>
                <span className="flex-1">{r.text}</span>
              </li>
            ))}
          </ul>
        </section>

        <section
          className={cn(
            "rounded-2xl border-2 px-5 py-4 sm:px-6 sm:py-5",
            style.actionTone === "bull" && "border-bull/30 bg-bull/5",
            style.actionTone === "bear" && "border-bear/30 bg-bear/5",
            style.actionTone === "neutral" && "border-border-subtle bg-bg-tertiary/50",
          )}
        >
          <p className="text-xs sm:text-sm uppercase tracking-widest text-text-tertiary font-semibold mb-3">
            操作建议
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {analysis.actions.map((a, i) => {
              const toneText =
                a.tone === "bull" ? "text-bull" : a.tone === "bear" ? "text-bear" : "text-text-primary";
              return (
                <div
                  key={i}
                  className="rounded-xl bg-bg-secondary/80 border border-border-subtle px-4 py-3"
                >
                  <p className="text-xs text-text-tertiary uppercase tracking-wider mb-1">{a.label}</p>
                  <p className={cn("text-lg sm:text-xl font-bold tabular-nums leading-tight", toneText)}>{a.value}</p>
                </div>
              );
            })}
          </div>
        </section>

        <section>
          <button
            type="button"
            onClick={() => setShowRaw((v) => !v)}
            className="w-full flex items-center justify-between rounded-xl bg-bg-tertiary/40 hover:bg-bg-tertiary/70 transition-colors px-4 py-2.5 text-sm text-text-secondary"
          >
            <span className="flex items-center gap-2">
              {showRaw ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              查看支撑压力位 + 原始指标
            </span>
            <span className="text-[11px] text-text-tertiary">
              {showRaw ? "收起" : "展开"}
            </span>
          </button>

          {showRaw && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="rounded-xl border border-border-subtle p-4">
                <p className="text-[11px] text-text-tertiary uppercase tracking-wider mb-2 font-semibold">
                  关键价位
                </p>
                <div className="space-y-1.5 text-sm tabular-nums">
                  <SRRow label="压力 R2" value={analysis.sr.r2} tone="bear" />
                  <SRRow label="压力 R1" value={analysis.sr.r1} tone="bear" faint />
                  <SRRow label="现价" value={analysis.sr.price} tone="neutral" bold />
                  <SRRow label="支撑 S1" value={analysis.sr.s1} tone="bull" faint />
                  <SRRow label="支撑 S2" value={analysis.sr.s2} tone="bull" />
                </div>
              </div>

              <div className="rounded-xl border border-border-subtle p-4">
                <p className="text-[11px] text-text-tertiary uppercase tracking-wider mb-2 font-semibold">
                  指标数据
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                  <Stat label="MA20" value={analysis.raw.ma20} />
                  <Stat label="MA60" value={analysis.raw.ma60} />
                  <Stat label="EMA12/26" value={`${analysis.raw.ema12.toFixed(2)} / ${analysis.raw.ema26.toFixed(2)}`} plain />
                  <Stat label="MACD" value={analysis.raw.macd} />
                  <Stat label="RSI(14)" value={analysis.raw.rsi} />
                  <Stat label="ADX" value={analysis.raw.adx} />
                  <Stat label="+DI / -DI" value={`${analysis.raw.pdi.toFixed(1)} / ${analysis.raw.ndi.toFixed(1)}`} plain />
                  <Stat label="ATR" value={analysis.raw.atr} />
                  <Stat label="ATR%" value={analysis.raw.atrPct} suffix="%" />
                  <Stat label="量能趋势" value={analysis.raw.volTrend * 100} suffix="%" signed />
                  <Stat label="MA20 偏离" value={analysis.raw.ma20Bias} suffix="%" signed />
                </div>
              </div>
            </div>
          )}
        </section>
      </CardBody>
    </Card>
  );
}

function SRRow({
  label,
  value,
  tone,
  faint,
  bold,
}: {
  label: string;
  value: number;
  tone: "bull" | "bear" | "neutral";
  faint?: boolean;
  bold?: boolean;
}) {
  const color = tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-text-primary";
  return (
    <div className="flex items-center justify-between">
      <span className={cn("text-text-tertiary", faint && "opacity-60")}>{label}</span>
      <span className={cn("tabular-nums", color, faint && "opacity-60", bold && "font-semibold")}>
        {value.toFixed(2)}
      </span>
    </div>
  );
}

function Stat({
  label,
  value,
  suffix,
  signed,
  plain,
}: {
  label: string;
  value: number | string;
  suffix?: string;
  signed?: boolean;
  plain?: boolean;
}) {
  const display =
    plain || typeof value === "string"
      ? String(value)
      : signed
        ? `${value > 0 ? "+" : ""}${value.toFixed(2)}${suffix ?? ""}`
        : `${value.toFixed(2)}${suffix ?? ""}`;
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-text-tertiary text-xs">{label}</span>
      <span className="tabular-nums text-text-primary font-medium">{display}</span>
    </div>
  );
}

function analyze(
  candles: TrendAnalysisPanelProps["candles"],
  timeframe: string,
): Analysis | null {
  if (candles.length < 30) return null;

  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const volumes = candles.map((c) => c.volume);
  const price = closes[closes.length - 1];

  const ma20 = sma(closes, 20);
  const ma60 = sma(closes, 60);
  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdLine = macd(closes).macd;
  const rsi14 = rsi(closes, 14);
  const adxResult = adx(
    candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume })),
    14,
  );
  const adxArr = adxResult.adx;
  const pdiArr = adxResult.pdi;
  const ndiArr = adxResult.ndi;
  const atrArr = atr(
    candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume })),
    14,
  );
  const obvArr = obv(
    candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume })),
  );

  const i = closes.length - 1;
  const ma20v = ma20[i];
  const ma60v = ma60[i];
  const ema12v = ema12[i];
  const ema26v = ema26[i];
  const macdV = macdLine[i];
  const rsiV = rsi14[i];
  const adxV = adxArr[i];
  const pdiV = pdiArr[i];
  const ndiV = ndiArr[i];
  const atrV = atrArr[i];

  const reasons: Reason[] = [];

  if (ma20v > ma60v && price > ma20v) {
    reasons.push({
      stance: 1,
      text: "MA20 在 MA60 之上，价格站在双均线上方，多头格局",
      detail: `MA20=${ma20v.toFixed(2)} > MA60=${ma60v.toFixed(2)}, close=${price.toFixed(2)}`,
    });
  } else if (ma20v < ma60v && price < ma20v) {
    reasons.push({
      stance: -1,
      text: "MA20 在 MA60 之下，价格跌破双均线，空头格局",
      detail: `MA20=${ma20v.toFixed(2)} < MA60=${ma60v.toFixed(2)}, close=${price.toFixed(2)}`,
    });
  } else {
    reasons.push({
      stance: 0,
      text: "MA20 / MA60 缠绕，无明确方向",
      detail: `MA20=${ma20v.toFixed(2)}, MA60=${ma60v.toFixed(2)}`,
    });
  }

  if (ema12v > ema26v && macdV > 0) {
    reasons.push({
      stance: 1,
      text: "MACD 金叉，DIF 在零轴之上，多头动能延续",
      detail: `EMA12=${ema12v.toFixed(2)} > EMA26=${ema26v.toFixed(2)}, MACD=${macdV.toFixed(3)}`,
    });
  } else if (ema12v < ema26v && macdV < 0) {
    reasons.push({
      stance: -1,
      text: "MACD 死叉，DIF 在零轴之下，空头动能延续",
      detail: `EMA12=${ema12v.toFixed(2)} < EMA26=${ema26v.toFixed(2)}, MACD=${macdV.toFixed(3)}`,
    });
  } else {
    reasons.push({
      stance: 0,
      text: "MACD 在零轴附近纠缠，动能中性",
      detail: `MACD=${macdV.toFixed(3)}`,
    });
  }

  if (adxV > 25) {
    if (pdiV > ndiV) {
      reasons.push({
        stance: 1,
        text: `ADX ${adxV.toFixed(1)}，趋势强；+DI 占优，确认上升趋势`,
        detail: `ADX=${adxV.toFixed(1)}, +DI=${pdiV.toFixed(1)}, -DI=${ndiV.toFixed(1)}`,
      });
    } else {
      reasons.push({
        stance: -1,
        text: `ADX ${adxV.toFixed(1)}，趋势强；-DI 占优，确认下降趋势`,
        detail: `ADX=${adxV.toFixed(1)}, +DI=${pdiV.toFixed(1)}, -DI=${ndiV.toFixed(1)}`,
      });
    }
  } else if (adxV < 18) {
    reasons.push({
      stance: 0,
      text: `ADX ${adxV.toFixed(1)} 偏弱，无明显趋势行情`,
      detail: `ADX=${adxV.toFixed(1)}, +DI=${pdiV.toFixed(1)}, -DI=${ndiV.toFixed(1)}`,
    });
  } else {
    reasons.push({
      stance: pdiV > ndiV ? 1 : -1,
      text: `ADX ${adxV.toFixed(1)} 中性，趋势强度一般`,
      detail: `ADX=${adxV.toFixed(1)}, +DI=${pdiV.toFixed(1)}, -DI=${ndiV.toFixed(1)}`,
    });
  }

  if (rsiV > 70) {
    reasons.push({ stance: -1, text: `RSI ${rsiV.toFixed(0)} 进入超买区，谨防回调`, detail: `RSI=${rsiV.toFixed(1)}` });
  } else if (rsiV < 30) {
    reasons.push({ stance: 1, text: `RSI ${rsiV.toFixed(0)} 进入超卖区，可能反弹`, detail: `RSI=${rsiV.toFixed(1)}` });
  } else if (rsiV > 55) {
    reasons.push({ stance: 1, text: `RSI ${rsiV.toFixed(0)} 偏多区域，仍有上行空间`, detail: `RSI=${rsiV.toFixed(1)}` });
  } else if (rsiV < 45) {
    reasons.push({ stance: -1, text: `RSI ${rsiV.toFixed(0)} 偏空区域，动能偏弱`, detail: `RSI=${rsiV.toFixed(1)}` });
  } else {
    reasons.push({ stance: 0, text: `RSI ${rsiV.toFixed(0)} 中性区域`, detail: `RSI=${rsiV.toFixed(1)}` });
  }

  const obvRecent = obvArr.slice(-20);
  const obvChange = (obvRecent[obvRecent.length - 1] - obvRecent[0]) / (Math.abs(obvRecent[0]) + 1);
  if (obvChange > 0.1 && price > ma20v) {
    reasons.push({ stance: 1, text: "OBV 上升 + 价格在 MA20 之上，量价齐升", detail: `OBV 20根变化=${(obvChange * 100).toFixed(1)}%` });
  } else if (obvChange < -0.1 && price < ma20v) {
    reasons.push({ stance: -1, text: "OBV 下降 + 价格跌破 MA20，量价齐跌", detail: `OBV 20根变化=${(obvChange * 100).toFixed(1)}%` });
  } else if (Math.abs(obvChange) > 0.15) {
    reasons.push({
      stance: obvChange > 0 ? 1 : -1,
      text: `OBV ${obvChange > 0 ? "上升" : "下降"}，与价格${obvChange > 0 === price > ma20v ? "共振" : "背离"}`,
      detail: `OBV 20根变化=${(obvChange * 100).toFixed(1)}%`,
    });
  }

  reasons.sort((a, b) => Math.abs(b.stance) - Math.abs(a.stance));
  const topReasons = reasons.slice(0, 5);

  const stanceScore = topReasons.reduce((s, r) => s + r.stance, 0);
  const maxStance = topReasons.length;
  const rawScore = stanceScore / Math.max(1, maxStance);
  const score = Math.round(rawScore * 100);

  const atrPct = (atrV / price) * 100;
  const recentVol = volumes.slice(-5).reduce((a, b) => a + b, 0) / 5;
  const priorVol = volumes.slice(-25, -5).reduce((a, b) => a + b, 0) / 20;
  const volTrend = (recentVol - priorVol) / (priorVol + 1e-9);
  const ma20Bias = ((price - ma20v) / ma20v) * 100;

  let verdict: Verdict;
  if (atrPct > 5 && Math.abs(score) < 30) verdict = "crisis";
  else if (adxV < 18 && Math.abs(score) < 25) verdict = "choppy";
  else if (score >= 60) verdict = "strong_bull";
  else if (score >= 20) verdict = "bull";
  else if (score > -20) verdict = "neutral";
  else if (score > -60) verdict = "bear";
  else verdict = "strong_bear";

  const pivot = (highs[i] + lows[i] + closes[i]) / 3;
  const range = highs[i] - lows[i];
  const sr = {
    price,
    r1: pivot * 2 - lows[i],
    r2: pivot + range,
    s1: pivot * 2 - highs[i],
    s2: pivot - range,
  };

  return {
    verdict,
    score,
    headline: buildHeadline(verdict, adxV, pdiV, ndiV, ma20Bias),
    reasons: topReasons,
    sr,
    actions: buildActions(verdict, sr, ma20v, atrV, timeframe),
    raw: {
      ma20: ma20v, ma60: ma60v, ema12: ema12v, ema26: ema26v,
      macd: macdV, rsi: rsiV, adx: adxV, pdi: pdiV, ndi: ndiV,
      atr: atrV, atrPct, volTrend, ma20Bias,
    },
  };
}

function buildHeadline(
  verdict: Verdict,
  adx: number,
  pdi: number,
  ndi: number,
  ma20Bias: number,
): string {
  const dirWord = pdi > ndi ? "上行" : "下行";
  const strong = adx > 25 ? "强趋势" : adx > 18 ? "弱趋势" : "无明显趋势";
  switch (verdict) {
    case "strong_bull": return `强趋势确认 ${dirWord}，价格偏离 MA20 +${ma20Bias.toFixed(1)}%`;
    case "bull": return `${strong}偏多，关注 MA20 附近支撑`;
    case "neutral": return `多空均衡，${strong}，等突破再操作`;
    case "choppy": return `区间震荡行情，建议高抛低吸`;
    case "bear": return `${strong}偏空，关注 MA20 附近压力`;
    case "strong_bear": return `强趋势确认 ${dirWord}，价格偏离 MA20 ${ma20Bias.toFixed(1)}%`;
    case "crisis": return `波动率异常，流动性可能下降`;
  }
}

function buildActions(
  verdict: Verdict,
  sr: { price: number; r1: number; r2: number; s1: number; s2: number },
  ma20: number,
  atr: number,
  timeframe: string,
): { label: string; value: string; tone: "bull" | "bear" | "neutral" }[] {
  const fmt = (n: number) => n.toFixed(2);
  switch (verdict) {
    case "strong_bull":
      return [
        { label: "做多入场", value: `MA20 附近 (~${fmt(ma20)}) 不破做多`, tone: "bull" },
        { label: "目标位", value: `R1 ${fmt(sr.r1)} → R2 ${fmt(sr.r2)}`, tone: "bull" },
        { label: "止损", value: `≤ ${fmt(atr * 2)} / ${timeframe}`, tone: "neutral" },
      ];
    case "bull":
      return [
        { label: "做多入场", value: `回踩 MA20 (~${fmt(ma20)}) 不破`, tone: "bull" },
        { label: "目标位", value: `R1 ${fmt(sr.r1)}`, tone: "bull" },
        { label: "止损", value: `MA20 下方 ${fmt(ma20 * 0.99)}`, tone: "neutral" },
      ];
    case "neutral":
      return [
        { label: "操作", value: "观望为主，等突破 S1 / R1", tone: "neutral" },
        { label: "区间", value: `${fmt(sr.s1)} ~ ${fmt(sr.r1)}`, tone: "neutral" },
        { label: "止损", value: `≤ ${fmt(atr * 2)} / ${timeframe}`, tone: "neutral" },
      ];
    case "choppy":
      return [
        { label: "操作", value: "区间内高抛低吸", tone: "neutral" },
        { label: "区间", value: `${fmt(sr.s1)} ~ ${fmt(sr.r1)}`, tone: "neutral" },
        { label: "止损", value: `≤ ${fmt(atr * 1.5)} / ${timeframe}`, tone: "neutral" },
      ];
    case "bear":
      return [
        { label: "做空入场", value: `反弹至 MA20 (~${fmt(ma20)}) 不破做空`, tone: "bear" },
        { label: "目标位", value: `S1 ${fmt(sr.s1)}`, tone: "bear" },
        { label: "止损", value: `MA20 上方 ${fmt(ma20 * 1.01)}`, tone: "neutral" },
      ];
    case "strong_bear":
      return [
        { label: "做空入场", value: `反弹 MA20 (~${fmt(ma20)}) 不破持有`, tone: "bear" },
        { label: "目标位", value: `S1 ${fmt(sr.s1)} → S2 ${fmt(sr.s2)}`, tone: "bear" },
        { label: "止损", value: `≤ ${fmt(atr * 2)} / ${timeframe}`, tone: "neutral" },
      ];
    case "crisis":
      return [
        { label: "操作", value: "减仓或离场观望", tone: "neutral" },
        { label: "等待", value: "波动率回归正常水平", tone: "neutral" },
        { label: "止损", value: `≤ ${fmt(atr * 1.5)} / ${timeframe}`, tone: "neutral" },
      ];
  }
}
