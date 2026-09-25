/**
 * 技术指标计算模块 — 全部纯函数，输入 OHLCV 数组，输出对应指标数组。
 * 与 lightweight-charts 解耦，可独立单测。
 */

export interface OHLC {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** 简单移动平均 SMA */
export function sma(values: number[], period: number): number[] {
  const out: number[] = new Array(values.length).fill(NaN);
  if (values.length < period) return out;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += values[i];
  out[period - 1] = sum / period;
  for (let i = period; i < values.length; i++) {
    sum += values[i] - values[i - period];
    out[i] = sum / period;
  }
  return out;
}

/** 指数移动平均 EMA */
export function ema(values: number[], period: number): number[] {
  const out: number[] = new Array(values.length).fill(NaN);
  if (values.length === 0) return out;
  const k = 2 / (period + 1);
  out[0] = values[0];
  for (let i = 1; i < values.length; i++) {
    out[i] = values[i] * k + out[i - 1] * (1 - k);
  }
  return out;
}

/** RSI 相对强弱指标（14 周期标准） */
export function rsi(values: number[], period = 14): number[] {
  const out: number[] = new Array(values.length).fill(NaN);
  if (values.length < period + 1) return out;
  const gains: number[] = new Array(values.length).fill(0);
  const losses: number[] = new Array(values.length).fill(0);
  for (let i = 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    gains[i] = d > 0 ? d : 0;
    losses[i] = d < 0 ? -d : 0;
  }
  let avgG = 0;
  let avgL = 0;
  for (let i = 1; i <= period; i++) {
    avgG += gains[i];
    avgL += losses[i];
  }
  avgG /= period;
  avgL /= period;
  out[period] = 100 - 100 / (1 + avgG / (avgL || 1e-10));
  for (let i = period + 1; i < values.length; i++) {
    avgG = (avgG * (period - 1) + gains[i]) / period;
    avgL = (avgL * (period - 1) + losses[i]) / period;
    const rs = avgG / (avgL || 1e-10);
    out[i] = 100 - 100 / (1 + rs);
  }
  return out;
}

export interface BollingerBands {
  middle: number[];
  upper: number[];
  lower: number[];
}

export function bollingerBands(values: number[], period = 20, numStd = 2): BollingerBands {
  const middle = sma(values, period);
  const upper: number[] = new Array(values.length).fill(NaN);
  const lower: number[] = new Array(values.length).fill(NaN);
  for (let i = period - 1; i < values.length; i++) {
    let sumSq = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const d = values[j] - middle[i];
      sumSq += d * d;
    }
    const std = Math.sqrt(sumSq / period);
    upper[i] = middle[i] + numStd * std;
    lower[i] = middle[i] - numStd * std;
  }
  return { middle, upper, lower };
}

export interface MACDResult {
  macd: number[];
  signal: number[];
  histogram: number[];
}

/** MACD = EMA12 - EMA26，信号线 = MACD 的 EMA9 */
export function macd(values: number[], fast = 12, slow = 26, signal = 9): MACDResult {
  const emaFast = ema(values, fast);
  const emaSlow = ema(values, slow);
  const macdLine = values.map((_, i) => emaFast[i] - emaSlow[i]);
  const signalLine = ema(macdLine, signal);
  const histogram = macdLine.map((m, i) => m - signalLine[i]);
  return { macd: macdLine, signal: signalLine, histogram };
}

export interface KDJResult {
  k: number[];
  d: number[];
  j: number[];
}

/** KDJ 随机指标（9 周期，3 周期 SMA 平滑） */
export function kdj(candles: OHLC[], period = 9, kSmooth = 3, dSmooth = 3): KDJResult {
  const n = candles.length;
  const k: number[] = new Array(n).fill(NaN);
  const d: number[] = new Array(n).fill(NaN);
  const j: number[] = new Array(n).fill(NaN);
  let prevK = 50;
  let prevD = 50;
  for (let i = period - 1; i < n; i++) {
    const slice = candles.slice(i - period + 1, i + 1);
    const high = Math.max(...slice.map((c) => c.high));
    const low = Math.min(...slice.map((c) => c.low));
    const close = candles[i].close;
    const rsv = high === low ? 50 : ((close - low) / (high - low)) * 100;
    const curK = (prevK * (kSmooth - 1) + rsv) / kSmooth;
    const curD = (prevD * (dSmooth - 1) + curK) / dSmooth;
    k[i] = curK;
    d[i] = curD;
    j[i] = 3 * curK - 2 * curD;
    prevK = curK;
    prevD = curD;
  }
  return { k, d, j };
}

/** OBV 能量潮（On Balance Volume） */
export function obv(candles: OHLC[]): number[] {
  const out: number[] = new Array(candles.length).fill(0);
  for (let i = 1; i < candles.length; i++) {
    if (candles[i].close > candles[i - 1].close) {
      out[i] = out[i - 1] + candles[i].volume;
    } else if (candles[i].close < candles[i - 1].close) {
      out[i] = out[i - 1] - candles[i].volume;
    } else {
      out[i] = out[i - 1];
    }
  }
  return out;
}

/** VWAP 成交量加权平均价（锚定日内，本实现为滚动 24 根 K 线 VWAP） */
export function vwap(candles: OHLC[], lookback = 24): number[] {
  const out: number[] = new Array(candles.length).fill(NaN);
  for (let i = 0; i < candles.length; i++) {
    const start = Math.max(0, i - lookback + 1);
    let pv = 0;
    let v = 0;
    for (let j = start; j <= i; j++) {
      const typical = (candles[j].high + candles[j].low + candles[j].close) / 3;
      pv += typical * candles[j].volume;
      v += candles[j].volume;
    }
    out[i] = v > 0 ? pv / v : candles[i].close;
  }
  return out;
}

/** ATR (Average True Range) — 平均真实波幅，常用于波动率和仓位管理 */
export function atr(candles: OHLC[], period = 14): number[] {
  const n = candles.length;
  const tr: number[] = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    if (i === 0) {
      tr[i] = candles[i].high - candles[i].low;
    } else {
      tr[i] = Math.max(
        candles[i].high - candles[i].low,
        Math.abs(candles[i].high - candles[i - 1].close),
        Math.abs(candles[i].low - candles[i - 1].close),
      );
    }
  }
  // Wilder 平滑（等同 EMA with k = 1/period）
  const out: number[] = new Array(n).fill(NaN);
  if (n < period) return out;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += tr[i];
  out[period - 1] = sum / period;
  for (let i = period; i < n; i++) {
    out[i] = (out[i - 1] * (period - 1) + tr[i]) / period;
  }
  return out;
}

/** ADX (Average Directional Index) — 趋势强度（不计方向） */
export function adx(candles: OHLC[], period = 14): { adx: number[]; pdi: number[]; ndi: number[] } {
  const n = candles.length;
  const pdi: number[] = new Array(n).fill(NaN);
  const ndi: number[] = new Array(n).fill(NaN);
  const adxArr: number[] = new Array(n).fill(NaN);
  if (n < period + 1) return { adx: adxArr, pdi, ndi };

  const trArr: number[] = new Array(n).fill(0);
  const pDM: number[] = new Array(n).fill(0);
  const nDM: number[] = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    const upMove = candles[i].high - candles[i - 1].high;
    const dnMove = candles[i - 1].low - candles[i].low;
    pDM[i] = upMove > dnMove && upMove > 0 ? upMove : 0;
    nDM[i] = dnMove > upMove && dnMove > 0 ? dnMove : 0;
    trArr[i] = Math.max(
      candles[i].high - candles[i].low,
      Math.abs(candles[i].high - candles[i - 1].close),
      Math.abs(candles[i].low - candles[i - 1].close),
    );
  }

  // Wilder smooth
  let trSum = 0;
  let pDmSum = 0;
  let nDmSum = 0;
  for (let i = 1; i <= period; i++) {
    trSum += trArr[i];
    pDmSum += pDM[i];
    nDmSum += nDM[i];
  }
  let trSmooth = trSum;
  let pDmSmooth = pDmSum;
  let nDmSmooth = nDmSum;
  pdi[period] = (pDmSmooth / (trSmooth || 1e-10)) * 100;
  ndi[period] = (nDmSmooth / (trSmooth || 1e-10)) * 100;
  const dx: number[] = new Array(n).fill(NaN);
  dx[period] = (Math.abs(pdi[period] - ndi[period]) / ((pdi[period] + ndi[period]) || 1e-10)) * 100;

  for (let i = period + 1; i < n; i++) {
    trSmooth = trSmooth - trSmooth / period + trArr[i];
    pDmSmooth = pDmSmooth - pDmSmooth / period + pDM[i];
    nDmSmooth = nDmSmooth - nDmSmooth / period + nDM[i];
    pdi[i] = (pDmSmooth / (trSmooth || 1e-10)) * 100;
    ndi[i] = (nDmSmooth / (trSmooth || 1e-10)) * 100;
    dx[i] = (Math.abs(pdi[i] - ndi[i]) / ((pdi[i] + ndi[i]) || 1e-10)) * 100;
  }

  let dxSum = 0;
  for (let i = period; i < period * 2; i++) dxSum += dx[i] || 0;
  adxArr[period * 2 - 1] = dxSum / period;
  for (let i = period * 2; i < n; i++) {
    adxArr[i] = (adxArr[i - 1] * (period - 1) + (dx[i] || 0)) / period;
  }
  return { adx: adxArr, pdi, ndi };
}

/** CCI (Commodity Channel Index) — 商品通道指标，识别周期反转 */
export function cci(candles: OHLC[], period = 20): number[] {
  const n = candles.length;
  const tp = candles.map((c) => (c.high + c.low + c.close) / 3);
  const out: number[] = new Array(n).fill(NaN);
  if (n < period) return out;
  for (let i = period - 1; i < n; i++) {
    const slice = tp.slice(i - period + 1, i + 1);
    const mean = slice.reduce((s, v) => s + v, 0) / period;
    const md = slice.reduce((s, v) => s + Math.abs(v - mean), 0) / period;
    out[i] = md > 0 ? (tp[i] - mean) / (0.015 * md) : 0;
  }
  return out;
}

/** Williams %R — 超买超卖（-100 ~ 0） */
export function williamsR(candles: OHLC[], period = 14): number[] {
  const n = candles.length;
  const out: number[] = new Array(n).fill(NaN);
  if (n < period) return out;
  for (let i = period - 1; i < n; i++) {
    const slice = candles.slice(i - period + 1, i + 1);
    const high = Math.max(...slice.map((c) => c.high));
    const low = Math.min(...slice.map((c) => c.low));
    out[i] = high === low ? -50 : ((high - candles[i].close) / (high - low)) * -100;
  }
  return out;
}

/** Stochastic (KD) — 随机指标（与 KDJ 区别：KDJ 有 J 线） */
export function stochastic(
  candles: OHLC[],
  kPeriod = 14,
  dPeriod = 3,
): { k: number[]; d: number[] } {
  const n = candles.length;
  const k: number[] = new Array(n).fill(NaN);
  const d: number[] = new Array(n).fill(NaN);
  if (n < kPeriod) return { k, d };
  for (let i = kPeriod - 1; i < n; i++) {
    const slice = candles.slice(i - kPeriod + 1, i + 1);
    const high = Math.max(...slice.map((c) => c.high));
    const low = Math.min(...slice.map((c) => c.low));
    k[i] = high === low ? 50 : ((candles[i].close - low) / (high - low)) * 100;
  }
  // d = SMA of k
  const kFilled = k.map((v) => (Number.isNaN(v) ? 50 : v));
  const smaD = sma(kFilled, dPeriod);
  for (let i = 0; i < n; i++) d[i] = smaD[i];
  return { k, d };
}

/** MFI (Money Flow Index) — 量价加权 RSI（0-100） */
export function mfi(candles: OHLC[], period = 14): number[] {
  const n = candles.length;
  const out: number[] = new Array(n).fill(NaN);
  if (n < period + 1) return out;
  const tp = candles.map((c) => (c.high + c.low + c.close) / 3);
  const rawFlow = candles.map((c, i) => tp[i] * c.volume);
  const pos: number[] = new Array(n).fill(0);
  const neg: number[] = new Array(n).fill(0);
  for (let i = 1; i < n; i++) {
    if (tp[i] > tp[i - 1]) pos[i] = rawFlow[i];
    else if (tp[i] < tp[i - 1]) neg[i] = rawFlow[i];
  }
  let posSum = 0;
  let negSum = 0;
  for (let i = 1; i <= period; i++) {
    posSum += pos[i];
    negSum += neg[i];
  }
  const mfRatio = negSum === 0 ? 100 : posSum / negSum;
  out[period] = 100 - 100 / (1 + mfRatio);
  for (let i = period + 1; i < n; i++) {
    posSum = posSum - pos[i - period] + pos[i];
    negSum = negSum - neg[i - period] + neg[i];
    const r = negSum === 0 ? 100 : posSum / negSum;
    out[i] = 100 - 100 / (1 + r);
  }
  return out;
}

/** Parabolic SAR (Stop And Reverse) — 趋势跟踪止损 */
export function sar(
  candles: OHLC[],
  step = 0.02,
  maximum = 0.2,
): { trend: ("up" | "down")[]; value: number[] } {
  const n = candles.length;
  const trend: ("up" | "down")[] = new Array(n).fill("up");
  const value: number[] = new Array(n).fill(NaN);
  if (n < 2) return { trend, value };

  let isUp = candles[1].close >= candles[0].close;
  trend[0] = isUp ? "up" : "down";
  trend[1] = isUp ? "up" : "down";
  let af = step;
  let ep = isUp ? candles[0].high : candles[0].low;
  value[0] = isUp ? candles[0].low : candles[0].high;

  for (let i = 1; i < n; i++) {
    const prev = value[i - 1];
    const cur = prev + af * (ep - prev);
    const c = candles[i];
    const cl = c.low;
    const ch = c.high;
    if (isUp) {
      const reverse = cl < cur;
      if (!reverse) {
        if (ch > ep) {
          ep = ch;
          af = Math.min(af + step, maximum);
        }
        value[i] = Math.min(cur, candles[i - 1].low, candles[i - 2]?.low ?? cur);
        trend[i] = "up";
      } else {
        isUp = false;
        value[i] = ep;
        ep = cl;
        af = step;
        trend[i] = "down";
      }
    } else {
      const reverse = ch > cur;
      if (!reverse) {
        if (cl < ep) {
          ep = cl;
          af = Math.min(af + step, maximum);
        }
        value[i] = Math.max(cur, candles[i - 1].high, candles[i - 2]?.high ?? cur);
        trend[i] = "down";
      } else {
        isUp = true;
        value[i] = ep;
        ep = ch;
        af = step;
        trend[i] = "up";
      }
    }
  }
  return { trend, value };
}

/** Supertrend — ATR 趋势指标 */
export function supertrend(
  candles: OHLC[],
  period = 10,
  multiplier = 3.0,
): { trend: ("up" | "down")[]; value: number[] } {
  const n = candles.length;
  const value: number[] = new Array(n).fill(NaN);
  const trend: ("up" | "down")[] = new Array(n).fill("up");
  const atrArr = atr(candles, period);
  if (n < period) return { trend, value };

  for (let i = period - 1; i < n; i++) {
    const c = candles[i];
    const hl2 = (c.high + c.low) / 2;
    const upper = hl2 + multiplier * atrArr[i];
    const lower = hl2 - multiplier * atrArr[i];
    if (i === period - 1) {
      value[i] = c.close > hl2 ? lower : upper;
      trend[i] = c.close > hl2 ? "up" : "down";
      continue;
    }
    const prevClose = candles[i - 1].close;
    const prevUpper = value[i - 1];
    const prevLower = value[i - 1];
    const finalUpper = upper < prevUpper || prevClose > prevUpper ? upper : prevUpper;
    const finalLower = lower > prevLower || prevClose < prevLower ? lower : prevLower;
    if (prevClose <= prevUpper && c.close > finalUpper) {
      value[i] = finalLower;
      trend[i] = "up";
    } else if (prevClose >= prevLower && c.close < finalLower) {
      value[i] = finalUpper;
      trend[i] = "down";
    } else {
      value[i] = trend[i - 1] === "up" ? finalLower : finalUpper;
      trend[i] = trend[i - 1];
    }
  }
  return { trend, value };
}

/** Keltner Channels — EMA ± ATR 包络线 */
export function keltnerChannels(
  candles: OHLC[],
  period = 20,
  multiplier = 2.0,
): { upper: number[]; middle: number[]; lower: number[] } {
  const closes = candles.map((c) => c.close);
  const middle = ema(closes, period);
  const atrArr = atr(candles, period);
  const upper = middle.map((m, i) => (Number.isNaN(m) || Number.isNaN(atrArr[i]) ? NaN : m + multiplier * atrArr[i]));
  const lower = middle.map((m, i) => (Number.isNaN(m) || Number.isNaN(atrArr[i]) ? NaN : m - multiplier * atrArr[i]));
  return { upper, middle, lower };
}

/** Ichimoku Cloud (一目均衡表) — 综合趋势系统 */
export function ichimoku(
  candles: OHLC[],
  conv = 9,
  base = 26,
  spanB = 52,
): {
  tenkan: number[];
  kijun: number[];
  senkouA: number[];
  senkouB: number[];
  chikou: number[];
} {
  const n = candles.length;
  const tenkan: number[] = new Array(n).fill(NaN);
  const kijun: number[] = new Array(n).fill(NaN);
  const senkouA: number[] = new Array(n).fill(NaN);
  const senkouB: number[] = new Array(n).fill(NaN);
  const chikou: number[] = new Array(n).fill(NaN);

  const highAt = (i: number, p: number) => Math.max(...candles.slice(Math.max(0, i - p + 1), i + 1).map((c) => c.high));
  const lowAt = (i: number, p: number) => Math.min(...candles.slice(Math.max(0, i - p + 1), i + 1).map((c) => c.low));

  for (let i = 0; i < n; i++) {
    if (i >= conv - 1) tenkan[i] = (highAt(i, conv) + lowAt(i, conv)) / 2;
    if (i >= base - 1) kijun[i] = (highAt(i, base) + lowAt(i, base)) / 2;
    if (i >= Math.max(conv, base) - 1) senkouA[i] = (tenkan[i] + kijun[i]) / 2;
    if (i >= spanB - 1) senkouB[i] = (highAt(i, spanB) + lowAt(i, spanB)) / 2;
    chikou[i] = candles[i].close;
  }
  return { tenkan, kijun, senkouA, senkouB, chikou };
}

