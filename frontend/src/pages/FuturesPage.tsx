/**
 * FuturesPage — 合约交易计算器独立页面（LeftSidebar 入口）
 *
 * 与 K 线页面下的 RightSidebar 内嵌版本共享同一个 FuturesContractPanel 组件，
 * 数据源都是全局 symbolContextStore。
 */

import { Repeat } from "lucide-react";

import { FuturesContractPanel } from "@/components/FuturesContractPanel";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { useSymbolContext } from "@/stores/symbolContextStore";

export function FuturesPage() {
  const ctx = useSymbolContext();
  const symbol = ctx.symbol || "BTCUSDT";
  const hasCandles = ctx.candles.length > 0;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <Repeat className="w-4 h-4 text-text-tertiary" />
          <h1 className="text-xl font-semibold tracking-tight">合约交易计算器</h1>
          <span className="text-xs text-text-tertiary">· {symbol} · USDT 永续</span>
        </div>
        <p className="text-xs text-text-tertiary">
          多/空方向 · 杠杆切换 · 爆仓价估算 · 资金费率 · 持仓量 · 止盈止损
        </p>
      </header>

      {!hasCandles && (
        <Card>
          <CardHeader>
            <h2 className="text-sm font-medium text-text-primary">等待 K 线数据</h2>
          </CardHeader>
          <CardBody className="text-text-tertiary text-sm space-y-1">
            <p>合约计算器依赖 K 线自动计算标记价、24h 涨跌、资金费率参考。</p>
            <p>
              请先打开
              <a href="/" className="text-bull mx-1 underline hover:no-underline">K 线页面</a>
              选择币种和时间周期，回到此处自动激活。
            </p>
          </CardBody>
        </Card>
      )}

      <FuturesContractPanel />

      <Card>
        <CardHeader>
          <h3 className="text-sm font-medium text-text-primary">公式说明</h3>
        </CardHeader>
        <CardBody className="text-xs text-text-tertiary space-y-1 leading-relaxed">
          <p>· 全仓爆仓价（多）= 开仓均价 × (1 - 1/杠杆 + MMR)</p>
          <p>· 全仓爆仓价（空）= 开仓均价 × (1 + 1/杠杆 - MMR)</p>
          <p>· 逐仓爆仓价 = 开仓均价 × (1 ∓ 1/杠杆)</p>
          <p>· MMR 默认 0.5%（Binance USDⓈ-M 维持保证金率），风险金 0.5%</p>
          <p>· 名义价值 = 数量 × 标记价</p>
          <p>· 所需保证金 = 名义价值 / 杠杆</p>
          <p className="pt-1 text-[10px]">计算基于本地参数，实际以交易所为准</p>
        </CardBody>
      </Card>
    </div>
  );
}
