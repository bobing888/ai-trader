/**
 * 指标注册表 + 配色常量 — 单一数据源
 *
 * 为什么独立成模块：
 * KlineChart.tsx 之前把这些常量 + 类型与 React 组件放在同一文件，触发 Vite Fast Refresh
 * 的 mixed export 检测 → 整个文件 full reload → KlineChart 在 prefs 重 mount 时
 * 撞 React StrictMode 双调用，导致
 *   "Rendered more hooks than during the previous render" race。
 *
 * 修法：常量 / 类型 / registry 全部移到本模块，KlineChart.tsx 只 import 使用，
 * 不再有 mixed export，Fast Refresh 走 hot module replacement（只重渲染组件本身，
 * 不重新执行模块顶层代码 → useState / useRef 顺序保持稳定）。
 */

export const COLORS = {
  bg: "#140c0c",
  text: "#ffffff",
  textSecondary: "rgba(255, 240, 220, 0.66)",
  textTertiary: "rgba(255, 240, 220, 0.42)",
  grid: "rgba(255, 240, 220, 0.06)",
  border: "rgba(255, 240, 220, 0.08)",
  bull: "#22c55e",
  bear: "#ef4444",
  // 主图指标配色（MA 暖色系 · BOLL 冷色系 — 高对比，深色背景友好）
  ma5: "#fef3c7", // warm white — 极短周期，紧贴价格
  ma10: "#fbbf24", // amber
  ma20: "#fb923c", // orange
  ma30: "#f43f5e", // rose
  ma60: "#a855f7", // violet
  ema12: "#06b6d4", // cyan
  ema26: "#0ea5e9", // sky
  ema50: "#3b82f6", // blue
  bbUpper: "rgba(96, 165, 250, 0.85)", // sky blue — 上轨
  bbMid: "#22d3ee", // cyan — 中轨（视觉锚）
  bbLower: "rgba(96, 165, 250, 0.85)", // sky blue — 下轨
  vwap: "#f472b6",
  // 副图指标
  rsi: "#fb923c",
  rsi6: "#fbbf24",
  rsi24: "#f97316",
  macd: "#38bdf8",
  macdSignal: "#fbbf24",
  macdHist: "#a78bfa",
  kdjK: "#fb923c",
  kdjD: "#22d3ee",
  kdjJ: "#a78bfa",
  obv: "#94a3b8",
  stochK: "#fb923c",
  stochD: "#22d3ee",
  cci: "#a855f7",
  wr: "#22d3ee",
  mfi: "#f472b6",
  adx: "#fb923c",
  pdi: "#22c55e",
  ndi: "#ef4444",
  atr: "#94a3b8",
  sar: "#ec4899",
  supertrend: "#22d3ee",
  keltnerU: "rgba(96, 165, 250, 0.6)",
  keltnerM: "#60a5fa",
  keltnerL: "rgba(96, 165, 250, 0.6)",
  ichiTenkan: "#fb923c",
  ichiKijun: "#3b82f6",
  ichiSpanA: "rgba(34, 197, 94, 0.25)",
  ichiSpanB: "rgba(239, 68, 68, 0.25)",
} as const;

export type OverlayId =
  | "ma5" | "ma10" | "ma20" | "ma30" | "ma60"
  | "ema12" | "ema26" | "ema50"
  | "boll" | "vwap" | "sar" | "supertrend" | "keltner" | "ichimoku";

export type PanelId =
  | "rsi" | "rsi6" | "rsi24" | "macd" | "kdj" | "obv"
  | "stoch" | "cci" | "wr" | "mfi" | "adx" | "atr";

export type IndicatorId = OverlayId | PanelId;

export interface IndicatorDef {
  id: IndicatorId;
  label: string;
  color: string;
  overlay: boolean;
  /** Optional sub-plots for indicators with multiple lines (boll=3, ichimoku=2, keltner=3) */
  extraPlots?: { id: string; color: string }[];
}

export const OVERLAY_DEFS: IndicatorDef[] = [
  { id: "ma5", label: "MA 5", color: COLORS.ma5, overlay: true },
  { id: "ma10", label: "MA 10", color: COLORS.ma10, overlay: true },
  { id: "ma20", label: "MA 20", color: COLORS.ma20, overlay: true },
  { id: "ma30", label: "MA 30", color: COLORS.ma30, overlay: true },
  { id: "ma60", label: "MA 60", color: COLORS.ma60, overlay: true },
  { id: "ema12", label: "EMA 12", color: COLORS.ema12, overlay: true },
  { id: "ema26", label: "EMA 26", color: COLORS.ema26, overlay: true },
  { id: "ema50", label: "EMA 50", color: COLORS.ema50, overlay: true },
  {
    id: "boll", label: "BOLL", color: COLORS.bbMid, overlay: true,
    extraPlots: [
      { id: "upper", color: COLORS.bbUpper },
      { id: "lower", color: COLORS.bbLower },
    ],
  },
  { id: "vwap", label: "VWAP", color: COLORS.vwap, overlay: true },
  { id: "sar", label: "SAR", color: COLORS.sar, overlay: true },
  { id: "supertrend", label: "ST", color: COLORS.supertrend, overlay: true },
  {
    id: "keltner", label: "KC", color: COLORS.keltnerM, overlay: true,
    extraPlots: [
      { id: "upper", color: COLORS.keltnerU },
      { id: "lower", color: COLORS.keltnerL },
    ],
  },
  {
    id: "ichimoku", label: "ICH", color: COLORS.ichiTenkan, overlay: true,
    extraPlots: [
      { id: "kijun", color: COLORS.ichiKijun },
      { id: "spanA", color: COLORS.ichiSpanA },
      { id: "spanB", color: COLORS.ichiSpanB },
    ],
  },
];

export const PANEL_DEFS: IndicatorDef[] = [
  { id: "rsi", label: "RSI 14", color: COLORS.rsi, overlay: false },
  { id: "rsi6", label: "RSI 6", color: COLORS.rsi6, overlay: false },
  { id: "rsi24", label: "RSI 24", color: COLORS.rsi24, overlay: false },
  { id: "macd", label: "MACD", color: COLORS.macd, overlay: false },
  { id: "kdj", label: "KDJ", color: COLORS.kdjK, overlay: false },
  { id: "obv", label: "OBV", color: COLORS.obv, overlay: false },
  { id: "stoch", label: "Stoch", color: COLORS.stochK, overlay: false },
  { id: "cci", label: "CCI", color: COLORS.cci, overlay: false },
  { id: "wr", label: "WR", color: COLORS.wr, overlay: false },
  { id: "mfi", label: "MFI", color: COLORS.mfi, overlay: false },
  {
    id: "adx", label: "ADX", color: COLORS.adx, overlay: false,
    extraPlots: [
      { id: "pdi", color: COLORS.pdi },
      { id: "ndi", color: COLORS.ndi },
    ],
  },
  { id: "atr", label: "ATR", color: COLORS.atr, overlay: false },
];

export const ALL_DEFS = [...OVERLAY_DEFS, ...PANEL_DEFS];

/** 默认开启的主图 overlay（与 DEFAULT_PREFS 保持一致）— 用于控制标签显示等视觉细节 */
export const DEFAULT_ENABLED_OVERLAYS = new Set<string>([
  "ma20", "ma30", "ema50", "boll",
]);
