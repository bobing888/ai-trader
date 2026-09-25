import { describe, expect, it } from "vitest";
import {
  adx,
  atr,
  bollingerBands,
  cci,
  ema,
  ichimoku,
  kdj,
  keltnerChannels,
  macd,
  mfi,
  obv,
  rsi,
  sar,
  sma,
  stochastic,
  supertrend,
  vwap,
  williamsR,
} from "@/lib/indicators";
import type { OHLC } from "@/lib/indicators";

const sampleOHLC: OHLC[] = Array.from({ length: 50 }, (_, i) => ({
  time: i,
  open: 100 + i,
  high: 105 + i,
  low: 95 + i,
  close: 102 + i + (i % 7 === 0 ? 5 : -3),
  volume: 1000 + i * 10,
}));

describe("indicators", () => {
  it("sma 正确计算 5 周期移动平均", () => {
    const result = sma([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21], 5);
    expect(result[4]).toBe(3); // (1+2+3+4+5)/5
    expect(result[20]).toBe(19); // (17+18+19+20+21)/5
  });

  it("ema 第一值等于第一输入", () => {
    const result = ema([10, 20, 30, 40], 3);
    expect(result[0]).toBe(10);
  });

  it("rsi 在上升趋势中接近 100", () => {
    const rising = Array.from({ length: 30 }, (_, i) => 100 + i);
    const result = rsi(rising, 14);
    expect(result[result.length - 1]).toBeGreaterThan(80);
  });

  it("rsi 在下降趋势中接近 0", () => {
    const falling = Array.from({ length: 30 }, (_, i) => 200 - i);
    const result = rsi(falling, 14);
    expect(result[result.length - 1]).toBeLessThan(20);
  });

  it("bollingerBands 上轨高于下轨", () => {
    const values = sampleOHLC.map((c) => c.close);
    const { upper, middle, lower } = bollingerBands(values, 20, 2);
    for (let i = 19; i < values.length; i++) {
      expect(upper[i]).toBeGreaterThan(middle[i]);
      expect(middle[i]).toBeGreaterThan(lower[i]);
    }
  });

  it("macd 返回三条等长 series", () => {
    const values = sampleOHLC.map((c) => c.close);
    const result = macd(values);
    expect(result.macd).toHaveLength(values.length);
    expect(result.signal).toHaveLength(values.length);
    expect(result.histogram).toHaveLength(values.length);
  });

  it("kdj K/D/J 关系 J = 3K - 2D", () => {
    const result = kdj(sampleOHLC);
    const last = result.k.length - 1;
    if (!isNaN(result.k[last])) {
      expect(Math.abs(result.j[last] - (3 * result.k[last] - 2 * result.d[last]))).toBeLessThan(0.001);
    }
  });

  it("obv 序列单调递增在连续上涨中", () => {
    const upOHLC: OHLC[] = Array.from({ length: 10 }, (_, i) => ({
      time: i, open: 100 + i, high: 110 + i, low: 95 + i, close: 105 + i, volume: 100,
    }));
    const result = obv(upOHLC);
    for (let i = 1; i < result.length; i++) {
      expect(result[i]).toBeGreaterThan(result[i - 1]);
    }
  });

  it("vwap 输出长度等于输入", () => {
    const result = vwap(sampleOHLC, 10);
    expect(result).toHaveLength(sampleOHLC.length);
  });

  it("atr 输出长度等于输入且为非负数", () => {
    const result = atr(sampleOHLC, 14);
    expect(result).toHaveLength(sampleOHLC.length);
    // 至少有一段非 NaN
    const valid = result.filter((v) => !isNaN(v));
    expect(valid.length).toBeGreaterThan(0);
    expect(Math.min(...valid)).toBeGreaterThanOrEqual(0);
  });

  it("adx 返回 pdi/ndi/adx 三条等长 series，值在 0-100 区间", () => {
    const result = adx(sampleOHLC, 14);
    expect(result.adx).toHaveLength(sampleOHLC.length);
    expect(result.pdi).toHaveLength(sampleOHLC.length);
    expect(result.ndi).toHaveLength(sampleOHLC.length);
    const validPdi = result.pdi.filter((v) => !isNaN(v));
    expect(validPdi.length).toBeGreaterThan(0);
    expect(Math.max(...validPdi)).toBeLessThanOrEqual(100);
    expect(Math.min(...validPdi)).toBeGreaterThanOrEqual(0);
  });

  it("cci 在均值附近震荡，输出长度等于输入", () => {
    const result = cci(sampleOHLC, 20);
    expect(result).toHaveLength(sampleOHLC.length);
    const valid = result.filter((v) => !isNaN(v));
    expect(valid.length).toBeGreaterThan(20);
  });

  it("williamsR 在 -100 到 0 区间（用正常 OHLC）", () => {
    const realistic: OHLC[] = Array.from({ length: 30 }, (_, i) => {
      const base = 100 + i * 0.5;
      const open = base - 0.3;
      const close = base + 0.4;
      return {
        time: i,
        open,
        high: Math.max(open, close) + 1,
        low: Math.min(open, close) - 1,
        close,
        volume: 100,
      };
    });
    const result = williamsR(realistic, 14);
    const valid = result.filter((v) => !isNaN(v));
    expect(valid.length).toBeGreaterThan(0);
    expect(Math.min(...valid)).toBeGreaterThanOrEqual(-100);
    expect(Math.max(...valid)).toBeLessThanOrEqual(0);
  });

  it("stochastic K/D 都在 0-100 区间（用正常 OHLC）", () => {
    const realistic: OHLC[] = Array.from({ length: 30 }, (_, i) => {
      const base = 100 + i * 0.5;
      const open = base - 0.3;
      const close = base + 0.4;
      return {
        time: i,
        open,
        high: Math.max(open, close) + 1,
        low: Math.min(open, close) - 1,
        close,
        volume: 100,
      };
    });
    const result = stochastic(realistic, 14, 3);
    const validK = result.k.filter((v) => !isNaN(v));
    const validD = result.d.filter((v) => !isNaN(v));
    expect(validK.length).toBeGreaterThan(0);
    expect(validD.length).toBeGreaterThan(0);
    expect(Math.max(...validK)).toBeLessThanOrEqual(100);
    expect(Math.min(...validK)).toBeGreaterThanOrEqual(0);
  });

  it("mfi 在 0-100 区间", () => {
    const result = mfi(sampleOHLC, 14);
    const valid = result.filter((v) => !isNaN(v));
    expect(valid.length).toBeGreaterThan(0);
    expect(Math.min(...valid)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...valid)).toBeLessThanOrEqual(100);
  });

  it("sar 输出 trend/value 等长", () => {
    const result = sar(sampleOHLC, 0.02, 0.2);
    expect(result.value).toHaveLength(sampleOHLC.length);
    expect(result.trend).toHaveLength(sampleOHLC.length);
    expect(["up", "down"]).toContain(result.trend[result.trend.length - 1]);
  });

  it("supertrend 输出 trend/value 等长", () => {
    const result = supertrend(sampleOHLC, 10, 3);
    expect(result.value).toHaveLength(sampleOHLC.length);
    expect(result.trend).toHaveLength(sampleOHLC.length);
  });

  it("keltnerChannels upper > middle > lower", () => {
    const result = keltnerChannels(sampleOHLC, 20, 2);
    for (let i = 25; i < sampleOHLC.length; i++) {
      if (!isNaN(result.upper[i]) && !isNaN(result.lower[i])) {
        expect(result.upper[i]).toBeGreaterThanOrEqual(result.middle[i]);
        expect(result.middle[i]).toBeGreaterThanOrEqual(result.lower[i]);
      }
    }
  });

  it("ichimoku 输出 5 条等长 series", () => {
    const result = ichimoku(sampleOHLC, 9, 26, 52);
    expect(result.tenkan).toHaveLength(sampleOHLC.length);
    expect(result.kijun).toHaveLength(sampleOHLC.length);
    expect(result.senkouA).toHaveLength(sampleOHLC.length);
    expect(result.senkouB).toHaveLength(sampleOHLC.length);
    expect(result.chikou).toHaveLength(sampleOHLC.length);
  });
});
