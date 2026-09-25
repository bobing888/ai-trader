/**
 * TrendAnalysisPanel — K 线图下方的实时市场趋势分析面板。
 * 完全前端计算（基于已有 indicators.ts 纯函数），不依赖额外 API，
 * 这样不会拖慢 K 线渲染，也不会增加后端压力。
 *
 * 输出：
 *  - 综合判读（bull / bear / choppy / crisis）
 *  - 多空评分（-100 ~ +100）
 *  - 量能趋势
 *  - 趋势强度（ADX）
 *  - 波动率（ATR%）
 *  - 关键支撑/压力位（最近 N 根 K 线的 swing）
 *  - 共识建议（来自多指标共振的入场/离场信号）
 */

import { useMemo } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  ChevronRight,
  Layers,
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
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

export interface TrendAnalysisPanelProps {
  candles: Array<{ time: number; open: number; high: number; low: number; close: number; volume: number }>;
  symbol: string;
  timeframe: string;
}

type Verdict = "strong_bull" | "bull" | "neutral" | "bear" | "strong_bear" | "choppy" | "crisis";

interface VerdictStyle {
  label: string;
  color: string; // text class
  bg: string;
  ring: string;
  icon: typeof TrendingUp;
  description: string;
}

const VERDICT_STYLES: Record<Verdict, VerdictStyle> = {
  strong_bull: {
    label: "强势多头",
    color: "text-bull",
    bg: "bg-bull/10",
    ring: "ring-bull/40",
    icon: TrendingUp,
    description: "多指标共振向上，趋势强劲，可顺势做多。",
  },
  bull: {
    label: "偏多震荡",
    color: "text-bull/90",
    bg: "bg-bull/5",
    ring: "ring-bull/30",
    icon: ArrowUpRight,
    description: "多头占优但动能减弱，关注回调企稳做多。",
  },
  neutral: {
    label: "中性盘整",
    color: "text-text-secondary",
    bg: "bg-bg-tertiary",
    ring: "ring-border-subtle",
    icon: Minus,
    description: "多空力量均衡，建议观望等待方向突破。",
  },
  choppy: {
    label: "震荡洗盘",
    color: "text-warning",
    bg: "bg-warning/10",
    ring: "ring-warning/30",
    icon: Activity,
    description: "价格在区间内反复，建议高抛低吸，止损严格。",
  },
  bear: {
    label: "偏空回落",
    color: "text-bear/90",
    bg: "bg-bear/5",
    ring: "ring-bear/30",
    icon: ArrowDownRight,
    description: "空头占优，反弹做空优于抄底。",
  },
  strong_bear: {
    label: "强势空头",
    color: "text-bear",
    bg: "bg-bear/10",
    ring: "ring-bear/40",
    icon: TrendingDown,
    description: "多指标共振向下，趋势强劲，可顺势做空。",
  },
  crisis: {
    label: "高风险 / 危机",
    color: "text-danger",
    bg: "bg-danger/10",
    ring: "ring-danger/40",
    icon: AlertTriangle,
    description: "波动率急剧上升，流动性变差，建议减仓或观望。",
  },
};

interface IndicatorScore {
  name: string;
  score: number; // -1 ~ +1
  reason: string;
  weight: number;
}

export function TrendAnalysisPanel({ candles, symbol, timeframe }: TrendAnalysisPanelProps) {
  const analysis = useMemo(() => analyze(candles, timeframe), [candles, timeframe]);

  if (!analysis) {
    return null;
  }

  const style = VERDICT_STYLES[analysis.verdict];
  const Icon = style.icon;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-text-tertiary" />
          <h2 className="text-sm font-medium text-text-primary">市场趋势分析</h2>
          <span className="text-xs text-text-tertiary">
            {symbol} · {timeframe}
          </span>
        </div>
        <span className="text-[10px] text-text-tertiary uppercase tracking-wider">实时计算 · 基于最近 100 根 K 线</span>
      </CardHeader>
      <CardBody className="space-y-4">
        {/* Top: Verdict + score gauge */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
          <div className={cn("rounded-xl border border-border-subtle p-4 flex flex-col gap-2", style.bg)}>
            <div className="flex items-center gap-2">
              <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center ring-1", style.bg, style.ring)}>
                <Icon className={cn("w-4 h-4", style.color)} />
              </div>
              <div>
                <p className="text-[10px] text-text-tertiary uppercase tracking-wider">综合判读</p>
                <p className={cn("text-lg font-semibold leading-tight", style.color)}>{style.label}</p>
              </div>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">{style.description}</p>
          </div>

          {/* Score bar */}
          <div className="rounded-xl border border-border-subtle p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] text-text-tertiary uppercase tracking-wider">多空力量对比</span>
              <span className="text-xs text-text-secondary tabular-nums">
                {analysis.score > 0 ? "+" : ""}{analysis.score.toFixed(0)} / 100
              </span>
            </div>
            <div className="relative h-2.5 rounded-full overflow-hidden bg-bg-tertiary">
              <div
                className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 bg-bear/60"
                style={{ width: `${Math.min(50, Math.abs(analysis.score) / 2)}%`, transform: analysis.score >= 0 ? undefined : `translateX(-100%)` }}
              />
              <div
                className={cn(
                  "absolute top-0 bottom-0 left-1/2 rounded-full transition-all",
                  analysis.score >= 0 ? "bg-bull" : "bg-bear",
                )}
                style={{
                  width: `${Math.min(50, Math.abs(analysis.score) / 2)}%`,
                  transform: analysis.score >= 0 ? "translateX(0)" : "translateX(-100%)",
                }}
              />
            </div>
            <div className="flex justify-between mt-1.5">
              <span className="text-[10px] text-bear">空头</span>
              <span className="text-[10px] text-text-tertiary">0</span>
              <span className="text-[10px] text-bull">多头</span>
            </div>
          </div>
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricTile
            label="趋势强度 (ADX)"
            value={analysis.metrics.adx.toFixed(1)}
            hint={analysis.metrics.adx > 25 ? "有趋势" : analysis.metrics.adx > 18 ? "弱趋势" : "无趋势"}
            tone={analysis.metrics.adx > 25 ? "bull" : "neutral"}
          />
          <MetricTile
            label="波动率 (ATR%)"
            value={`${analysis.metrics.atrPct.toFixed(2)}%`}
            hint={analysis.metrics.atrPct > 3 ? "高波动" : analysis.metrics.atrPct > 1.2 ? "正常" : "低波动"}
            tone={analysis.metrics.atrPct > 3 ? "warning" : "neutral"}
          />
          <MetricTile
            label="量能趋势"
            value={analysis.metrics.volTrend > 0 ? `+${(analysis.metrics.volTrend * 100).toFixed(0)}%` : `${(analysis.metrics.volTrend * 100).toFixed(0)}%`}
            hint={analysis.metrics.volTrend > 0.15 ? "放量" : analysis.metrics.volTrend < -0.15 ? "缩量" : "平量"}
            tone={analysis.metrics.volTrend > 0.15 ? "bull" : analysis.metrics.volTrend < -0.15 ? "bear" : "neutral"}
          />
          <MetricTile
            label="MA20 偏离"
            value={`${analysis.metrics.ma20Bias > 0 ? "+" : ""}${analysis.metrics.ma20Bias.toFixed(2)}%`}
            hint={Math.abs(analysis.metrics.ma20Bias) > 3 ? "偏离较大" : "贴合均线"}
            tone={analysis.metrics.ma20Bias > 0 ? "bull" : "bear"}
          />
        </div>

        {/* Indicator breakdown */}
        <div>
          <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-2">多指标共振</p>
          <div className="space-y-1.5">
            {analysis.indicatorScores.map((ind) => (
              <div key={ind.name} className="flex items-center gap-3 text-xs">
                <span className="w-16 text-text-tertiary">{ind.name}</span>
                <div className="flex-1 h-1.5 rounded-full bg-bg-tertiary relative overflow-hidden">
                  <div
                    className={cn(
                      "absolute top-0 bottom-0",
                      ind.score > 0 ? "bg-bull" : ind.score < 0 ? "bg-bear" : "bg-text-tertiary",
                    )}
                    style={{ width: `${Math.abs(ind.score) * 50}%`, left: ind.score >= 0 ? "50%" : `${50 - Math.abs(ind.score) * 50}%` }}
                  />
                </div>
                <span className={cn(
                  "w-24 truncate text-right",
                  ind.score > 0 ? "text-bull" : ind.score < 0 ? "text-bear" : "text-text-tertiary",
                )}>
                  {ind.score > 0 ? "+" : ""}{ind.score.toFixed(2)}
                </span>
                <span className="w-48 text-text-secondary truncate">{ind.reason}</span>
              </div>
            ))}
          </div>
        </div>

        {/* S/R levels + recommendation */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-xl border border-border-subtle p-3">
            <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-2">关键价位</p>
            <div className="space-y-1.5 text-xs">
              <SRRow label="压力 R3" value={analysis.sr.r3} tone="bear" />
              <SRRow label="压力 R2" value={analysis.sr.r2} tone="bear" />
              <SRRow label="压力 R1" value={analysis.sr.r1} tone="bear" faint />
              <SRRow label="现价" value={analysis.sr.price} tone="neutral" bold />
              <SRRow label="支撑 S1" value={analysis.sr.s1} tone="bull" faint />
              <SRRow label="支撑 S2" value={analysis.sr.s2} tone="bull" />
              <SRRow label="支撑 S3" value={analysis.sr.s3} tone="bull" />
            </div>
          </div>
          <div className="rounded-xl border border-border-subtle p-3">
            <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-2">策略建议</p>
            <ul className="space-y-1.5 text-xs text-text-secondary">
              {analysis.recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <ChevronRight className="w-3 h-3 mt-0.5 text-text-tertiary flex-shrink-0" />
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function MetricTile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  tone: "bull" | "bear" | "neutral" | "warning";
}) {
  const toneClass = {
    bull: "text-bull",
    bear: "text-bear",
    neutral: "text-text-secondary",
    warning: "text-warning",
  }[tone];
  return (
    <div className="rounded-xl border border-border-subtle p-3">
      <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">{label}</p>
      <p className={cn("text-base font-semibold tabular-nums", toneClass)}>{value}</p>
      <p className="text-[10px] text-text-tertiary mt-0.5">{hint}</p>
    </div>
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

// ── Pure compute ──────────────────────────────────────────────────────────────

interface Analysis {
  verdict: Verdict;
  score: number;
  metrics: {
    adx: number;
    atrPct: number;
    volTrend: number;
    ma20Bias: number;
  };
  indicatorScores: IndicatorScore[];
  sr: {
    price: number;
    r1: number; r2: number; r3: number;
    s1: number; s2: number; s3: number;
  };
  recommendations: string[];
}

function analyze(candles: TrendAnalysisPanelProps["candles"], timeframe: string): Analysis | null {
  if (candles.length < 30) return null;

  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const volumes = candles.map((c) => c.volume);
  const price = closes[closes.length - 1];

  // Indicators
  const ma20 = sma(closes, 20);
  const ma60 = sma(closes, 60);
  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdLine = macd(closes).macd;
  const rsi14 = rsi(closes, 14);
  const adxResult = adx(candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume })), 14);
  const adxArr = adxResult.adx;
  const atrArr = atr(candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume })), 14);
  const obvArr = obv(candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume })));

  // Last values
  const i = closes.length - 1;
  const ma20v = ma20[i];
  const ma60v = ma60[i];
  const ema12v = ema12[i];
  const ema26v = ema26[i];
  const macdV = macdLine[i];
  const rsiV = rsi14[i];
  const adxV = adxArr[i];
  const atrV = atrArr[i];

  // Multi-indicator scoring
  const indicators: IndicatorScore[] = [];

  // 1. MA cross (20/60)
  if (ma20v > ma60v && price > ma20v) {
    indicators.push({ name: "MA20/60", score: 0.8, reason: "MA20 在上，价格在双均线上方", weight: 1.0 });
  } else if (ma20v < ma60v && price < ma20v) {
    indicators.push({ name: "MA20/60", score: -0.8, reason: "MA20 在下，价格在双均线下方", weight: 1.0 });
  } else {
    indicators.push({ name: "MA20/60", score: 0, reason: "MA 缠绕，无方向", weight: 0.5 });
  }

  // 2. EMA cross (12/26)
  if (ema12v > ema26v && macdV > 0) {
    indicators.push({ name: "EMA12/26", score: 0.6, reason: "MACD 金叉且在零轴上方", weight: 0.8 });
  } else if (ema12v < ema26v && macdV < 0) {
    indicators.push({ name: "EMA12/26", score: -0.6, reason: "MACD 死叉且在零轴下方", weight: 0.8 });
  } else {
    indicators.push({ name: "EMA12/26", score: 0, reason: "MACD 与零轴纠缠", weight: 0.5 });
  }

  // 3. RSI
  if (rsiV > 70) {
    indicators.push({ name: "RSI(14)", score: -0.4, reason: `${rsiV.toFixed(0)} 超买，谨防回调`, weight: 0.7 });
  } else if (rsiV < 30) {
    indicators.push({ name: "RSI(14)", score: 0.4, reason: `${rsiV.toFixed(0)} 超卖，可能反弹`, weight: 0.7 });
  } else if (rsiV > 55) {
    indicators.push({ name: "RSI(14)", score: 0.3, reason: `${rsiV.toFixed(0)} 偏多区域`, weight: 0.6 });
  } else if (rsiV < 45) {
    indicators.push({ name: "RSI(14)", score: -0.3, reason: `${rsiV.toFixed(0)} 偏空区域`, weight: 0.6 });
  } else {
    indicators.push({ name: "RSI(14)", score: 0, reason: `${rsiV.toFixed(0)} 中性`, weight: 0.5 });
  }

  // 4. ADX trend strength
  if (adxV > 25 && ma20v > ma60v) {
    indicators.push({ name: "ADX", score: 0.5, reason: `ADX ${adxV.toFixed(1)} 强势上升趋势`, weight: 0.7 });
  } else if (adxV > 25 && ma20v < ma60v) {
    indicators.push({ name: "ADX", score: -0.5, reason: `ADX ${adxV.toFixed(1)} 强势下降趋势`, weight: 0.7 });
  } else {
    indicators.push({ name: "ADX", score: 0, reason: `ADX ${adxV.toFixed(1)} 无明显趋势`, weight: 0.4 });
  }

  // 5. Volume (OBV trend over last 20 bars)
  const obvRecent = obvArr.slice(-20);
  const obvChange = (obvRecent[obvRecent.length - 1] - obvRecent[0]) / (Math.abs(obvRecent[0]) + 1);
  if (obvChange > 0.1 && price > ma20v) {
    indicators.push({ name: "OBV", score: 0.4, reason: "量价齐升", weight: 0.6 });
  } else if (obvChange < -0.1 && price < ma20v) {
    indicators.push({ name: "OBV", score: -0.4, reason: "量价齐跌", weight: 0.6 });
  } else {
    indicators.push({ name: "OBV", score: 0, reason: "量价背离或中性", weight: 0.5 });
  }

  // Weighted score
  const totalWeight = indicators.reduce((s, x) => s + x.weight, 0);
  const rawScore = indicators.reduce((s, x) => s + x.score * x.weight, 0) / totalWeight;
  const score = Math.round(rawScore * 100);

  // Volatility (ATR%)
  const atrPct = (atrV / price) * 100;
  // Volume trend (recent 5 vs prior 20)
  const recentVol = volumes.slice(-5).reduce((a, b) => a + b, 0) / 5;
  const priorVol = volumes.slice(-25, -5).reduce((a, b) => a + b, 0) / 20;
  const volTrend = (recentVol - priorVol) / (priorVol + 1e-9);
  // MA20 bias
  const ma20Bias = ((price - ma20v) / ma20v) * 100;

  // Verdict
  let verdict: Verdict;
  if (atrPct > 5 && Math.abs(score) < 30) {
    verdict = "crisis";
  } else if (adxV < 18 && Math.abs(score) < 25) {
    verdict = "choppy";
  } else if (score >= 60) {
    verdict = "strong_bull";
  } else if (score >= 20) {
    verdict = "bull";
  } else if (score > -20) {
    verdict = "neutral";
  } else if (score > -60) {
    verdict = "bear";
  } else {
    verdict = "strong_bear";
  }

  // S/R levels (pivot + recent swing)
  const pivot = (highs[i] + lows[i] + closes[i]) / 3;
  const range = highs[i] - lows[i];
  const sr = {
    price,
    r1: pivot * 2 - lows[i],
    r2: pivot + range,
    r3: pivot * 2 - lows[i] + range,
    s1: pivot * 2 - highs[i],
    s2: pivot - range,
    s3: pivot * 2 - highs[i] - range,
  };

  // Recommendations
  const recs: string[] = [];
  if (verdict === "strong_bull") {
    recs.push(`顺势做多，回调至 MA20 (${ma20v.toFixed(2)}) 不破继续持有`);
    recs.push(`下一压力位 R2 ${sr.r2.toFixed(2)}，突破看 R3 ${sr.r3.toFixed(2)}`);
    if (rsiV > 70) recs.push("⚠️ RSI 超买，分批止盈");
  } else if (verdict === "bull") {
    recs.push(`回调企稳做多，止损放在 MA20 下方 ${(ma20v * 0.99).toFixed(2)}`);
    recs.push(`突破 R1 ${sr.r1.toFixed(2)} 加仓，目标 R2 ${sr.r2.toFixed(2)}`);
  } else if (verdict === "neutral") {
    recs.push("观望为主，等待方向突破 S1/R1 再行动");
    recs.push(`震荡区间 ${sr.s1.toFixed(2)} ~ ${sr.r1.toFixed(2)}，可高抛低吸`);
  } else if (verdict === "choppy") {
    recs.push(`区间震荡，区间 ${sr.s1.toFixed(2)} ~ ${sr.r1.toFixed(2)}`);
    recs.push("严格止损，避免追涨杀跌");
  } else if (verdict === "bear") {
    recs.push(`反弹至 MA20 (${ma20v.toFixed(2)}) 不破做空`);
    recs.push(`下看 S2 ${sr.s2.toFixed(2)}，跌破看 S3 ${sr.s3.toFixed(2)}`);
  } else if (verdict === "strong_bear") {
    recs.push(`顺势做空，反弹至 MA20 (${ma20v.toFixed(2)}) 不破继续持有`);
    recs.push(`下方支撑 S2 ${sr.s2.toFixed(2)} / S3 ${sr.s3.toFixed(2)}`);
    if (rsiV < 30) recs.push("⚠️ RSI 超卖，关注反弹力度");
  } else {
    recs.push("波动率异常，建议减仓观望");
    recs.push("等待波动率回归正常水平");
  }
  recs.push(`ATR 风险：单笔止损 ≤ ${(atrV * 2).toFixed(2)} / ${timeframe}`);

  return {
    verdict,
    score,
    metrics: { adx: adxV, atrPct, volTrend, ma20Bias },
    indicatorScores: indicators,
    sr,
    recommendations: recs,
  };
}
