/**
 * FuturesContractPanel — 合约交易计算器 + 风险监控面板。
 * 1. 杠杆多档位切换 (1x-50x)
 * 2. 多/空方向切换 + 仓位规模自动计算
 * 3. 爆仓价估算（全仓/逐仓两种模式）
 * 4. 资金费率 / 持仓量 / 强平风险指示
 * 5. 名义价值 / 所需保证金 / 风险收益比
 *
 * 公式：
 *  - 全仓爆仓价（多）= 开仓均价 * (1 - 1/杠杆 + MMR)
 *  - 全仓爆仓价（空）= 开仓均价 * (1 + 1/杠杆 - MMR)
 *  - 逐仓爆仓价（多）= 开仓均价 - 保证金/数量
 *  - 强平价取 max(0, ...)
 *  - MMR 默认 0.5%（Binance USDⓈ-M 维持保证金率），风险金 0.5%
 *  - 名义价值 = 数量 * 标记价
 *  - 所需保证金 = 名义价值 / 杠杆
 */

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  CircleDollarSign,
  Flame,
  Info,
  Minus,
  Plus,
  Repeat,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { useSymbolContext } from "@/stores/symbolContextStore";

interface FuturesContractPanelProps {
  /** 可选：从 store 读取 candles/symbol，为空时面板不渲染 */
  fallbackSymbol?: string;
}

type Side = "long" | "short";
type MarginMode = "cross" | "isolated";
type OrderType = "market" | "limit";

interface RiskLevel {
  level: "safe" | "warn" | "danger" | "liquidation";
  label: string;
  color: string;
  bg: string;
}

const LEVERAGE_OPTIONS = [1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125];
const MMR = 0.005; // 维持保证金率 0.5% (Binance 默认)

function fmt(n: number, digits = 2): string {
  if (!isFinite(n)) return "—";
  if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + "M";
  return n.toFixed(digits);
}

function computeLiquidationPrice(
  entryPrice: number,
  leverage: number,
  side: Side,
  marginMode: MarginMode,
): number {
  if (leverage <= 1) return side === "long" ? 0 : Infinity;
  if (marginMode === "isolated") {
    // 逐仓：亏完保证金即爆仓（不考虑 MMR）
    return side === "long" ? entryPrice * (1 - 1 / leverage) : entryPrice * (1 + 1 / leverage);
  }
  // 全仓：考虑 MMR + 维持
  const liqLong = entryPrice * (1 - 1 / leverage + MMR);
  const liqShort = entryPrice * (1 + 1 / leverage - MMR);
  return side === "long" ? Math.max(0, liqLong) : Math.max(0, liqShort);
}

function getRiskLevel(liqDistancePct: number, leverage: number): RiskLevel {
  // liqDistancePct 是正数（% 距离爆仓的百分比）
  if (leverage >= 75 && liqDistancePct < 3) return { level: "liquidation", label: "极危 · 随时强平", color: "text-danger", bg: "bg-danger/10" };
  if (leverage >= 50 && liqDistancePct < 5) return { level: "danger", label: "高风险", color: "text-danger", bg: "bg-danger/5" };
  if (liqDistancePct < 10) return { level: "warn", label: "中等风险", color: "text-warning", bg: "bg-warning/5" };
  return { level: "safe", label: "安全", color: "text-bull", bg: "bg-bull/5" };
}

export function FuturesContractPanel({ fallbackSymbol = "BTCUSDT" }: FuturesContractPanelProps = {}) {
  const ctx = useSymbolContext();
  const symbol = ctx.symbol || fallbackSymbol;
  const candles = ctx.candles;

  // hooks 必须在任何条件 return 之前调用 — 否则 K 线数据加载时
  // (candles 从 [] 变为非空) 触发 "Rendered more hooks than during the previous render" race。
  // 这里空 candles 状态下也持有 useState / useMemo，只是 markPrice / stats24h 退化为
  // 安全 default，UX 由下方早返回兜底。
  const [side, setSide] = useState<Side>("long");
  const [marginMode, setMarginMode] = useState<MarginMode>("isolated");
  const [orderType, setOrderType] = useState<OrderType>("market");
  const [leverage, setLeverage] = useState<number>(10);
  const [marginUSDT, setMarginUSDT] = useState<number>(1000);
  const [entryPrice, setEntryPrice] = useState<string>("");
  const [takeProfitPct, setTakeProfitPct] = useState<number>(2.5);
  const [stopLossPct, setStopLossPct] = useState<number>(1.5);

  const lastCandle = candles[candles.length - 1];
  const markPrice = lastCandle?.close ?? 0;
  const entry = entryPrice ? parseFloat(entryPrice) : markPrice;

  // 24h 波动率估算（用于资金费率 / 持仓量提示）
  const stats24h = useMemo(() => {
    const last = candles.slice(-24);
    if (last.length < 2) return { change: 0, high: 0, low: 0, vol: 0 };
    const first = last[0].open;
    const lastPx = last[last.length - 1].close;
    const high = Math.max(...last.map((c) => c.high));
    const low = Math.min(...last.map((c) => c.low));
    const vol = last.reduce((s, c) => s + c.volume, 0);
    return { change: ((lastPx - first) / first) * 100, high, low, vol };
  }, [candles]);

  // 模拟的资金费率（真实场景应从交易所 API 拉）
  const fundingRate = useMemo(() => {
    // 用 24h 涨跌幅和波动率做一个示意（真实应从 /api/futures/fundingRate 拉）
    const seed = (candles.length > 100 ? candles[100].close : 0) * 0.00001;
    const sign = stats24h.change >= 0 ? 1 : -1;
    return sign * (0.005 + Math.abs(stats24h.change) * 0.003 + seed) / 100;
  }, [stats24h.change, candles]);

  // 模拟持仓量
  const openInterestUSDT = useMemo(() => {
    // 名义持仓量（BTC 合约 ~ 50 亿 USDT 量级）
    return stats24h.vol * markPrice * 12;
  }, [stats24h.vol, markPrice]);

  // 计算
  const calc = useMemo(() => {
    const size = (marginUSDT * leverage) / entry; // 合约张数 / 单位
    const notional = size * entry; // 名义价值
    const liqPrice = computeLiquidationPrice(entry, leverage, side, marginMode);
    const liqDistance = ((entry - liqPrice) / entry) * 100;
    const liqDistanceAbs = Math.abs(liqDistance);
    const tpPrice = side === "long" ? entry * (1 + takeProfitPct / 100) : entry * (1 - takeProfitPct / 100);
    const slPrice = side === "long" ? entry * (1 - stopLossPct / 100) : entry * (1 + stopLossPct / 100);
    const tpPnl = side === "long" ? (tpPrice - entry) * size : (entry - tpPrice) * size;
    const slPnl = side === "long" ? (slPrice - entry) * size : (entry - slPrice) * size;
    const riskReward = Math.abs(tpPnl / (slPnl || -1e-9));
    const riskLevel = getRiskLevel(liqDistanceAbs, leverage);

    return { size, notional, liqPrice, liqDistance, liqDistanceAbs, tpPrice, slPrice, tpPnl, slPnl, riskReward, riskLevel };
  }, [entry, leverage, marginUSDT, side, marginMode, takeProfitPct, stopLossPct]);

  if (candles.length === 0) {
    return (
      <Card>
        <CardBody className="text-center text-text-tertiary text-sm py-12">
          合约计算器等待 K 线数据…打开 K 线页面后会自动激活。
        </CardBody>
      </Card>
    );
  }

  const RiskIcon = calc.riskLevel.level === "safe" ? TrendingUp : calc.riskLevel.level === "warn" ? AlertTriangle : Flame;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Repeat className="w-4 h-4 text-text-tertiary" />
          <h2 className="text-sm font-medium text-text-primary">合约交易计算器</h2>
          <span className="text-xs text-text-tertiary">{symbol} · USDT 永续</span>
        </div>
        <span className="text-[10px] text-text-tertiary uppercase tracking-wider flex items-center gap-1">
          <Info className="w-3 h-3" /> 计算基于本地参数，实际以交易所为准
        </span>
      </CardHeader>
      <CardBody className="space-y-4">
        {/* Top: market stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile label="标记价" value={markPrice.toFixed(2)} />
          <StatTile label="24h 涨跌" value={`${stats24h.change >= 0 ? "+" : ""}${stats24h.change.toFixed(2)}%`} tone={stats24h.change >= 0 ? "bull" : "bear"} />
          <StatTile label="资金费率" value={`${(fundingRate * 100).toFixed(4)}%`} hint="每 8h" tone={fundingRate >= 0 ? "bull" : "bear"} />
          <StatTile label="持仓量" value={`$${fmt(openInterestUSDT)}`} hint="24h 名义" />
        </div>

        {/* Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left: side + leverage + margin */}
          <div className="rounded-xl border border-border-subtle p-4 space-y-4">
            {/* Side toggle */}
            <div>
              <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1.5">方向</p>
              <div className="grid grid-cols-2 gap-1 p-1 rounded-lg bg-bg-tertiary">
                <button
                  onClick={() => setSide("long")}
                  className={cn(
                    "py-2 rounded-md text-sm font-medium transition-colors flex items-center justify-center gap-1.5",
                    side === "long" ? "bg-bull text-white shadow-sm" : "text-text-secondary hover:text-text-primary",
                  )}
                >
                  <TrendingUp className="w-3.5 h-3.5" />
                  做多 (Long)
                </button>
                <button
                  onClick={() => setSide("short")}
                  className={cn(
                    "py-2 rounded-md text-sm font-medium transition-colors flex items-center justify-center gap-1.5",
                    side === "short" ? "bg-bear text-white shadow-sm" : "text-text-secondary hover:text-text-primary",
                  )}
                >
                  <TrendingDown className="w-3.5 h-3.5" />
                  做空 (Short)
                </button>
              </div>
            </div>

            {/* Margin mode */}
            <div>
              <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1.5">保证金模式</p>
              <div className="grid grid-cols-2 gap-1 p-1 rounded-lg bg-bg-tertiary">
                <button
                  onClick={() => setMarginMode("isolated")}
                  className={cn(
                    "py-1.5 rounded-md text-xs font-medium transition-colors",
                    marginMode === "isolated" ? "bg-bg-secondary text-text-primary" : "text-text-secondary",
                  )}
                >
                  逐仓 (Isolated)
                </button>
                <button
                  onClick={() => setMarginMode("cross")}
                  className={cn(
                    "py-1.5 rounded-md text-xs font-medium transition-colors",
                    marginMode === "cross" ? "bg-bg-secondary text-text-primary" : "text-text-secondary",
                  )}
                >
                  全仓 (Cross)
                </button>
              </div>
            </div>

            {/* Leverage */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[10px] text-text-tertiary uppercase tracking-wider">杠杆倍数</p>
                <span className={cn(
                  "text-sm font-bold tabular-nums",
                  leverage >= 50 ? "text-danger" : leverage >= 20 ? "text-warning" : "text-bull",
                )}>
                  {leverage}x
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                {LEVERAGE_OPTIONS.map((lv) => (
                  <button
                    key={lv}
                    onClick={() => setLeverage(lv)}
                    className={cn(
                      "px-2.5 py-1 rounded-md text-xs font-medium tabular-nums transition-colors",
                      leverage === lv
                        ? lv >= 50
                          ? "bg-danger text-white"
                          : lv >= 20
                            ? "bg-warning text-bg-primary"
                            : "bg-bull text-white"
                        : "bg-bg-tertiary text-text-secondary hover:text-text-primary",
                    )}
                  >
                    {lv}x
                  </button>
                ))}
              </div>
              <input
                type="range"
                min={1}
                max={125}
                value={leverage}
                onChange={(e) => setLeverage(parseInt(e.target.value))}
                className="w-full mt-2 accent-bull"
              />
            </div>

            {/* Margin input */}
            <div>
              <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1.5">保证金 (USDT)</p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setMarginUSDT(Math.max(50, Math.round(marginUSDT / 2)))}
                  className="w-8 h-8 rounded-md bg-bg-tertiary hover:bg-bg-secondary flex items-center justify-center"
                >
                  <Minus className="w-3.5 h-3.5" />
                </button>
                <input
                  type="number"
                  value={marginUSDT}
                  onChange={(e) => setMarginUSDT(Math.max(50, parseFloat(e.target.value) || 0))}
                  className="flex-1 h-8 px-3 rounded-md bg-bg-tertiary text-sm text-center tabular-nums focus:outline-none focus:ring-1 focus:ring-bull"
                />
                <button
                  onClick={() => setMarginUSDT(marginUSDT * 2)}
                  className="w-8 h-8 rounded-md bg-bg-tertiary hover:bg-bg-secondary flex items-center justify-center"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex gap-1 mt-1.5">
                {[500, 1000, 5000, 10000].map((v) => (
                  <button
                    key={v}
                    onClick={() => setMarginUSDT(v)}
                    className={cn(
                      "flex-1 py-1 rounded text-[10px] tabular-nums",
                      marginUSDT === v ? "bg-bull/15 text-bull" : "bg-bg-tertiary text-text-tertiary hover:text-text-secondary",
                    )}
                  >
                    {v >= 1000 ? `${v / 1000}k` : v}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right: entry + TP/SL */}
          <div className="rounded-xl border border-border-subtle p-4 space-y-4">
            {/* Entry price */}
            <div>
              <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1.5">开仓价格</p>
              <div className="flex gap-1.5">
                <input
                  type="number"
                  value={entryPrice}
                  onChange={(e) => setEntryPrice(e.target.value)}
                  placeholder={`市价 ${markPrice.toFixed(2)}`}
                  className="flex-1 h-9 px-3 rounded-md bg-bg-tertiary text-sm tabular-nums focus:outline-none focus:ring-1 focus:ring-bull"
                />
                <button
                  onClick={() => setOrderType("market")}
                  className={cn(
                    "px-3 rounded-md text-xs font-medium",
                    orderType === "market" ? "bg-bull text-white" : "bg-bg-tertiary text-text-secondary",
                  )}
                >
                  市价
                </button>
                <button
                  onClick={() => setOrderType("limit")}
                  className={cn(
                    "px-3 rounded-md text-xs font-medium",
                    orderType === "limit" ? "bg-bull text-white" : "bg-bg-tertiary text-text-secondary",
                  )}
                >
                  限价
                </button>
              </div>
              <button
                onClick={() => setEntryPrice(markPrice.toFixed(2))}
                className="mt-1.5 text-[10px] text-bull hover:underline"
              >
                使用标记价 {markPrice.toFixed(2)}
              </button>
            </div>

            {/* Take profit */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[10px] text-bull uppercase tracking-wider">止盈 (Take Profit)</p>
                <span className="text-xs text-bull tabular-nums">+{takeProfitPct.toFixed(2)}%</span>
              </div>
              <input
                type="range"
                min={0.5}
                max={20}
                step={0.1}
                value={takeProfitPct}
                onChange={(e) => setTakeProfitPct(parseFloat(e.target.value))}
                className="w-full accent-bull"
              />
              <div className="flex items-center justify-between text-[10px] text-text-tertiary tabular-nums mt-0.5">
                <span>价格 {(side === "long" ? entry * (1 + takeProfitPct / 100) : entry * (1 - takeProfitPct / 100)).toFixed(2)}</span>
                <span>盈利 +${fmt(calc.tpPnl)}</span>
              </div>
            </div>

            {/* Stop loss */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[10px] text-bear uppercase tracking-wider">止损 (Stop Loss)</p>
                <span className="text-xs text-bear tabular-nums">-{stopLossPct.toFixed(2)}%</span>
              </div>
              <input
                type="range"
                min={0.5}
                max={20}
                step={0.1}
                value={stopLossPct}
                onChange={(e) => setStopLossPct(parseFloat(e.target.value))}
                className="w-full accent-bear"
              />
              <div className="flex items-center justify-between text-[10px] text-text-tertiary tabular-nums mt-0.5">
                <span>价格 {(side === "long" ? entry * (1 - stopLossPct / 100) : entry * (1 + stopLossPct / 100)).toFixed(2)}</span>
                <span>亏损 -${fmt(Math.abs(calc.slPnl))}</span>
              </div>
            </div>

            {/* R/R ratio */}
            <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-bg-tertiary">
              <span className="text-xs text-text-tertiary">盈亏比 (Risk/Reward)</span>
              <span className={cn(
                "text-sm font-semibold tabular-nums",
                calc.riskReward >= 2 ? "text-bull" : calc.riskReward >= 1 ? "text-warning" : "text-bear",
              )}>
                1 : {calc.riskReward.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Result panel */}
        <div className={cn("rounded-xl border p-4", calc.riskLevel.bg, "border-border-subtle")}>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <ResultTile label="仓位大小" value={`${fmt(calc.size, 4)} ${symbol.replace("USDT", "")}`} />
            <ResultTile label="名义价值" value={`$${fmt(calc.notional, 0)}`} />
            <ResultTile
              label={side === "long" ? "爆仓价 (多)" : "爆仓价 (空)"}
              value={calc.liqPrice > 0 ? calc.liqPrice.toFixed(2) : "0.00"}
              tone="danger"
            />
            <ResultTile
              label="距爆仓"
              value={`${calc.liqDistanceAbs.toFixed(2)}%`}
              tone={calc.liqDistanceAbs < 5 ? "danger" : calc.liqDistanceAbs < 10 ? "warning" : "bull"}
            />
            <div className={cn("flex flex-col justify-center px-3 py-2 rounded-lg", calc.riskLevel.bg)}>
              <span className="text-[10px] text-text-tertiary uppercase tracking-wider">风险等级</span>
              <span className={cn("text-sm font-semibold flex items-center gap-1", calc.riskLevel.color)}>
                <RiskIcon className="w-3.5 h-3.5" />
                {calc.riskLevel.label}
              </span>
            </div>
          </div>

          {/* Liquidation distance bar */}
          <div className="mt-3">
            <div className="flex items-center justify-between text-[10px] text-text-tertiary mb-1">
              <span>强平距离</span>
              <span>{leverage}x · {marginMode === "cross" ? "全仓" : "逐仓"} · MMR {(MMR * 100).toFixed(2)}%</span>
            </div>
            <div className="relative h-2 rounded-full bg-bg-tertiary overflow-hidden">
              <div
                className={cn(
                  "absolute top-0 bottom-0 left-0 rounded-full transition-all",
                  calc.liqDistanceAbs < 5 ? "bg-danger" : calc.liqDistanceAbs < 10 ? "bg-warning" : "bg-bull",
                )}
                style={{ width: `${Math.min(100, calc.liqDistanceAbs * 5)}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[10px] text-text-tertiary mt-1 tabular-nums">
              <span>0%</span>
              <span>10%</span>
              <span>20%+</span>
            </div>
          </div>
        </div>

        {/* Liquidation cascade visual */}
        <div className="rounded-xl border border-border-subtle p-3">
          <p className="text-[10px] text-text-tertiary uppercase tracking-wider mb-2">价格触发事件</p>
          <div className="space-y-1 text-xs">
            <CascadeRow icon={ChevronUp} tone="bull" label="止盈触发价" value={calc.tpPrice} pct={takeProfitPct} />
            <CascadeRow icon={CircleDollarSign} tone="neutral" label="开仓价" value={entry} pct={0} bold />
            <CascadeRow icon={ChevronDown} tone="warn" label={`${marginMode === "cross" ? "强平预警 (-75%)" : "逐仓强平"}`} value={calc.liqPrice} pct={-calc.liqDistanceAbs} />
            <CascadeRow icon={ChevronDown} tone="bear" label="止损触发价" value={calc.slPrice} pct={-stopLossPct} />
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "bull" | "bear" | "neutral";
}) {
  const color = tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-text-primary";
  return (
    <div className="rounded-xl border border-border-subtle p-3">
      <p className="text-[10px] text-text-tertiary uppercase tracking-wider">{label}</p>
      <p className={cn("text-base font-semibold tabular-nums mt-0.5", color)}>{value}</p>
      {hint && <p className="text-[10px] text-text-tertiary mt-0.5">{hint}</p>}
    </div>
  );
}

function ResultTile({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "bull" | "bear" | "neutral" | "warning" | "danger" }) {
  const color = {
    bull: "text-bull",
    bear: "text-bear",
    neutral: "text-text-primary",
    warning: "text-warning",
    danger: "text-danger",
  }[tone];
  return (
    <div className="px-3 py-2 rounded-lg bg-bg-tertiary">
      <p className="text-[10px] text-text-tertiary uppercase tracking-wider">{label}</p>
      <p className={cn("text-sm font-semibold tabular-nums mt-0.5", color)}>{value}</p>
    </div>
  );
}

function CascadeRow({
  icon: Icon,
  tone,
  label,
  value,
  pct,
  bold,
}: {
  icon: typeof TrendingUp;
  tone: "bull" | "bear" | "neutral" | "warn";
  label: string;
  value: number;
  pct: number;
  bold?: boolean;
}) {
  const color = tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : tone === "warn" ? "text-warning" : "text-text-primary";
  return (
    <div className="flex items-center justify-between">
      <span className="flex items-center gap-1.5 text-text-secondary">
        <Icon className={cn("w-3 h-3", color)} />
        {label}
      </span>
      <span className="flex items-center gap-2 tabular-nums">
        <span className={cn(color, bold && "font-semibold")}>{value.toFixed(2)}</span>
        <span className={cn("text-[10px]", pct > 0 ? "text-bull" : pct < 0 ? "text-bear" : "text-text-tertiary")}>
          {pct > 0 ? "+" : ""}{pct.toFixed(2)}%
        </span>
      </span>
    </div>
  );
}
