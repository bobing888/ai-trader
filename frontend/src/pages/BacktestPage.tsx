/**
 * BacktestPage — Phase 1 signal credibility.
 *
 * Replaces 100% mock data with real /api/backtest integration.
 * User picks symbol/timeframe/strategies → runs walk-forward backtest →
 * shows net PnL, Sharpe, hit rate, max drawdown, equity curve, per-trade table.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Loader2,
  AlertCircle,
} from "lucide-react";

import { Card, CardBody } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { EquityCurve } from "@/components/ui/EquityCurve";
import { cn } from "@/lib/utils";
import {
  runBacktest,
  type BacktestRequest,
  type BacktestResponse,
  type BacktestTrade,
} from "@/lib/backtestApi";

const SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"];
const TIMEFRAMES = [
  { value: "1m", label: "1 分钟" },
  { value: "5m", label: "5 分钟" },
  { value: "15m", label: "15 分钟" },
  { value: "1h", label: "1 小时" },
  { value: "4h", label: "4 小时" },
  { value: "1d", label: "1 天" },
];
const STRATEGIES = [
  { id: "MomentumStrategy", label: "动量趋势 (EMA + RSI)" },
  { id: "MeanReversionStrategy", label: "均值回归 (Bollinger)" },
  { id: "BreakoutStrategy", label: "区间突破" },
  { id: "VolatilityStrategy", label: "波动率策略" },
  { id: "SentimentStrategy", label: "情绪反向" },
  { id: "VolumeProfileStrategy", label: "量价共振" },
  { id: "MultiTimeframeStrategy", label: "多周期" },
  { id: "ConfluenceStrategy", label: "多指标共振" },
];

export function BacktestPage() {
  const { t } = useTranslation();
  const [symbol, setSymbol] = useState("BTC-USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [days, setDays] = useState(30);
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([
    "MomentumStrategy",
    "BreakoutStrategy",
  ]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);

  const handleRun = async () => {
    if (selectedStrategies.length === 0) {
      setError("至少选择一个策略");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const req: BacktestRequest = {
        symbol,
        timeframe: timeframe as BacktestRequest["timeframe"],
        strategies: selectedStrategies,
        days,
        fee_taker_bps: 8.0,
        slippage_bps: 5.0,
        min_confidence: 0.6,
        target_pct: 0.005,
        stop_pct: 0.003,
        max_hold_minutes: 60,
      };
      const data = await runBacktest(req);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const toggleStrategy = (id: string) => {
    setSelectedStrategies((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
          {t("backtest.title")}
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          基于真实 OKX K 线的 walk-forward 回测 · 含 OKX taker 0.08% / 滑点 0.05% 成本
        </p>
      </div>

      {/* Configuration */}
      <Card>
        <CardBody className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">回测配置</h3>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-text-tertiary block mb-1.5">币种</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-bg-tertiary border border-[rgba(255,240,220,0.06)] rounded-md px-3 py-2 text-sm text-text-primary"
              >
                {SYMBOLS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-tertiary block mb-1.5">时间周期</label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full bg-bg-tertiary border border-[rgba(255,240,220,0.06)] rounded-md px-3 py-2 text-sm text-text-primary"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf.value} value={tf.value}>{tf.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-text-tertiary block mb-1.5">回测天数</label>
              <input
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={(e) => setDays(Math.max(1, Math.min(365, Number(e.target.value) || 30)))}
                className="w-full bg-bg-tertiary border border-[rgba(255,240,220,0.06)] rounded-md px-3 py-2 text-sm text-text-primary"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={handleRun}
                disabled={loading || selectedStrategies.length === 0}
                className={cn(
                  "w-full h-10 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-colors",
                  loading
                    ? "bg-bg-tertiary text-text-tertiary cursor-not-allowed"
                    : "bg-accent text-bg-primary hover:bg-accent/90"
                )}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    回测中…
                  </>
                ) : (
                  <>
                    <Activity className="w-4 h-4" />
                    运行回测
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Strategy chips */}
          <div>
            <label className="text-xs text-text-tertiary block mb-2">
              策略组合（{selectedStrategies.length} 个已选）
            </label>
            <div className="flex flex-wrap gap-2">
              {STRATEGIES.map((s) => {
                const active = selectedStrategies.includes(s.id);
                return (
                  <button
                    key={s.id}
                    onClick={() => toggleStrategy(s.id)}
                    className={cn(
                      "px-3 py-1.5 rounded-full text-xs transition-colors",
                      active
                        ? "bg-accent/15 text-accent border border-accent/30"
                        : "bg-bg-tertiary text-text-secondary border border-[rgba(255,240,220,0.06)] hover:border-[rgba(255,240,220,0.15)]"
                    )}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Error */}
      {error && (
        <Card>
          <CardBody className="flex items-center gap-2 text-bear">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm">{error}</span>
          </CardBody>
        </Card>
      )}

      {/* Results */}
      {result && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              label="净收益"
              numericValue={result.summary.net_pnl_pct * 100}
              format={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`}
              tone={result.summary.net_pnl_pct >= 0 ? "bull" : "bear"}
              icon={<TrendingUp className="w-4 h-4" />}
            />
            <StatCard
              label="胜率"
              numericValue={result.summary.hit_rate * 100}
              format={(v) => `${v.toFixed(1)}%`}
              icon={<BarChart3 className="w-4 h-4" />}
            />
            <StatCard
              label="夏普比"
              numericValue={result.summary.sharpe_ratio}
              format={(v) => v.toFixed(2)}
              icon={<Activity className="w-4 h-4" />}
            />
            <StatCard
              label="最大回撤"
              numericValue={result.summary.max_drawdown_pct * 100}
              format={(v) => `${v.toFixed(2)}%`}
              tone="bear"
              icon={<TrendingDown className="w-4 h-4" />}
            />
          </div>

          {/* Equity curve */}
          <Card>
            <div className="px-5 py-4 border-b border-[rgba(255,240,220,0.06)]">
              <h3 className="text-sm font-semibold text-text-primary">净值曲线</h3>
              <p className="text-[11px] text-text-tertiary mt-0.5">
                {result.summary.total_trades} 笔模拟交易 · walk-forward CV · 含交易成本
              </p>
            </div>
            <div className="p-2">
              <EquityCurve
                data={result.equity_curve.map((p: { ts: string; equity: number }) => ({
                  value: p.equity,
                  label: new Date(p.ts).toISOString().slice(5, 16).replace("T", " "),
                }))}
                height={300}
              />
            </div>
          </Card>

          {/* Trade list */}
          <Card>
            <div className="px-5 py-4 border-b border-[rgba(255,240,220,0.06)]">
              <h3 className="text-sm font-semibold text-text-primary">
                模拟交易（{result.trades.length} 笔）
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-bg-tertiary/50 text-text-tertiary text-xs uppercase tracking-wide">
                  <tr>
                    <th className="px-4 py-2 text-left">入场时间</th>
                    <th className="px-4 py-2 text-left">策略</th>
                    <th className="px-4 py-2 text-right">入场价</th>
                    <th className="px-4 py-2 text-right">出场价</th>
                    <th className="px-4 py-2 text-right">置信度</th>
                    <th className="px-4 py-2 text-right">净 PnL</th>
                    <th className="px-4 py-2 text-left">结果</th>
                    <th className="px-4 py-2 text-right">持仓 (min)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[rgba(255,240,220,0.04)]">
                  {result.trades.slice(0, 50).map((t: BacktestTrade) => (
                    <tr key={t.id} className="hover:bg-bg-tertiary/30">
                      <td className="px-4 py-2 text-text-secondary text-xs tabular-nums">
                        {new Date(t.entry_time).toISOString().slice(0, 16).replace("T", " ")}
                      </td>
                      <td className="px-4 py-2 text-text-secondary text-xs">
                        {t.strategy_name}
                      </td>
                      <td className="px-4 py-2 text-right text-text-secondary tabular-nums">
                        {t.entry_price.toFixed(4)}
                      </td>
                      <td className="px-4 py-2 text-right text-text-secondary tabular-nums">
                        {t.exit_price.toFixed(4)}
                      </td>
                      <td className="px-4 py-2 text-right text-text-secondary tabular-nums">
                        {(t.calibrated_confidence ?? t.raw_confidence).toFixed(2)}
                      </td>
                      <td
                        className={cn(
                          "px-4 py-2 text-right tabular-nums font-medium",
                          t.net_pnl_pct >= 0 ? "text-bull" : "text-bear"
                        )}
                      >
                        {(t.net_pnl_pct * 100).toFixed(2)}%
                      </td>
                      <td className="px-4 py-2">
                        <OutcomeBadge outcome={t.outcome} />
                      </td>
                      <td className="px-4 py-2 text-right text-text-tertiary tabular-nums">
                        {t.holding_minutes}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.trades.length > 50 && (
                <div className="px-4 py-2 text-xs text-text-tertiary text-center">
                  仅显示前 50 笔 · 共 {result.trades.length} 笔
                </div>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: BacktestTrade["outcome"] }) {
  const map: Record<BacktestTrade["outcome"], { label: string; tone: string }> = {
    HIT_TP: { label: "✓ 止盈", tone: "bg-bull/15 text-bull border-bull/30" },
    HIT_SL: { label: "✗ 止损", tone: "bg-bear/15 text-bear border-bear/30" },
    EXPIRED: { label: "⏱ 到期", tone: "bg-bg-tertiary text-text-tertiary border-[rgba(255,240,220,0.06)]" },
    HOLD: { label: "持仓", tone: "bg-bg-tertiary text-text-secondary border-[rgba(255,240,220,0.06)]" },
  };
  const { label, tone } = map[outcome];
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border",
        tone
      )}
    >
      {label}
    </span>
  );
}