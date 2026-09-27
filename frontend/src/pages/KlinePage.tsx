/**
 * KlinePage — real-time K-line demo page.
 *
 * Connects to the OKX WebSocket bridge and renders live candles via
 * lightweight-charts.  Markers are stubbed (wired for PR #4).
 */

import { useState } from "react";

import { LightweightKlineChart } from "@/components/charts/LightweightKlineChart";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useRealtimeKlines, type Channel } from "@/lib/useRealtimeKlines";

const INSTS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "DOGE-USDT"] as const;

const CHANNELS: { label: string; value: Channel }[] = [
  { label: "1m", value: "candle1m" },
  { label: "5m", value: "candle5m" },
  { label: "15m", value: "candle15m" },
  { label: "1H", value: "candle1H" },
  { label: "4H", value: "candle4H" },
  { label: "1D", value: "candle1D" },
];

const STATUS_LABEL: Record<string, string> = {
  connecting: "连接中",
  connected: "已连接",
  reconnecting: "重连中",
  down: "已断开",
};

const STATUS_TONE: Record<string, "bull" | "bear" | "warning" | "info"> = {
  connecting: "info",
  connected: "bull",
  reconnecting: "warning",
  down: "bear",
};

function formatTimeAgo(date: Date | null): string {
  if (!date) return "—";
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s 前`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m 前`;
  return `${Math.floor(diffMin / 60)}h 前`;
}

export function KlinePage() {
  const [inst, setInst] = useState<typeof INSTS[number]>("BTC-USDT");
  const [channel, setChannel] = useState<Channel>("candle1m");

  const { candles, status, lastUpdate } = useRealtimeKlines(inst, channel);

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">实时 K 线</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            TradingView lightweight-charts · OKX 实时数据
          </p>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {/* Instrument selector */}
          <select
            value={inst}
            onChange={(e) => setInst(e.target.value as typeof INSTS[number])}
            className="bg-bg-secondary border border-[rgba(255,240,220,0.08)] text-sm text-text-primary rounded-full px-3 py-2 outline-none focus:border-accent/50 cursor-pointer"
          >
            {INSTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>

          {/* Channel selector */}
          <div className="flex rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.08)] p-0.5">
            {CHANNELS.map((c) => (
              <button
                key={c.value}
                onClick={() => setChannel(c.value)}
                className={`
                  px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer
                  ${channel === c.value
                    ? "bg-bg-tertiary text-text-primary"
                    : "text-text-secondary hover:text-text-primary"}
                `}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart */}
      <Card>
        <LightweightKlineChart
          candles={candles}
          height={520}
          markers={[]}
        />
      </Card>

      {/* Status bar */}
      <div className="flex items-center gap-4 text-xs text-text-secondary">
        <Badge tone={STATUS_TONE[status] ?? "info"} className="text-xs">
          {STATUS_LABEL[status] ?? status}
        </Badge>

        <span className="tabular-nums">
          {candles.length > 0
            ? `${candles.length} 根 K 线`
            : "等待数据…"}
        </span>

        {lastUpdate && (
          <span className="tabular-nums ml-auto">
            最新更新 {formatTimeAgo(lastUpdate)}
          </span>
        )}
      </div>
    </div>
  );
}
