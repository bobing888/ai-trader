import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { CandlestickChart, RefreshCw } from "lucide-react";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { IndicatorParamsModal } from "@/components/IndicatorParamsModal";
import { IndicatorTogglePanel } from "@/components/IndicatorTogglePanel";
import { KlineChart } from "@/components/KlineChart";
import {
  ALL_DEFS,
  type IndicatorDef,
} from "@/lib/indicatorRegistry";
import { TrendAnalysisPanel } from "@/components/TrendAnalysisPanel";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton, SkeletonStatCard } from "@/components/ui/Skeleton";
import { fetchKLines } from "@/lib/api";
import { loadPreferences, savePreferences, type ChartPreferences } from "@/lib/preferences";
import { useKlineStore } from "@/stores/klineStore";
import { useSymbolContext } from "@/stores/symbolContextStore";
import { useTranslation } from "react-i18next";

// 用户提到的 8 个指标 — 单一数据源；改这里 = 改面板里的指标范围
const UNIFIED_INDICATOR_IDS = ["ma30", "boll", "rsi", "rsi6", "rsi24", "macd", "kdj", "stoch"] as const;

/** 从 KlineChart 完整 registry 里筛出 8 个用户提到的指标定义 */
function getUnifiedDefs(): IndicatorDef[] {
  return ALL_DEFS.filter((d: IndicatorDef) =>
    (UNIFIED_INDICATOR_IDS as readonly string[]).includes(d.id),
  );
}

export function KlinePage() {
  const { symbol, timeframe, setSymbol, setTimeframe, hydrateFromSearch } = useKlineStore();
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // ── Preferences state ─────────────────────────────────────────────────────
  const [prefs, setPrefs] = useState<ChartPreferences | null>(null);
  // 当前编辑参数的指标 id（null = modal 关）
  const [editingId, setEditingId] = useState<string | null>(null);

  // Load prefs on mount
  useEffect(() => {
    void loadPreferences().then(setPrefs);
  }, []);

  const handleIndicatorToggle = async (indicatorId: string, enabled: boolean) => {
    if (!prefs) return;
    const next: ChartPreferences = {
      ...prefs,
      indicators: {
        ...prefs.indicators,
        [indicatorId]: { ...prefs.indicators[indicatorId], enabled },
      },
    };
    setPrefs(next);
    await savePreferences(next);
  };

  const handleSaveParams = async (
    indicatorId: string,
    params: Record<string, number | string | boolean>,
  ) => {
    if (!prefs) return;
    const next: ChartPreferences = {
      ...prefs,
      indicators: {
        ...prefs.indicators,
        [indicatorId]: { ...prefs.indicators[indicatorId], params },
      },
    };
    setPrefs(next);
    await savePreferences(next);
  };

  // URL → store: hydrate store from URL searchParams.
  useEffect(() => {
    hydrateFromSearch(searchParams);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Store → URL: after every store change, reflect to URL while preserving other params.
  useEffect(() => {
    const state = useKlineStore.getState();
    const urlSymbol = searchParams.get("symbol");
    const urlTf = searchParams.get("timeframe");
    const nextParams = new URLSearchParams(searchParams);
    if (state.symbol !== urlSymbol) nextParams.set("symbol", state.symbol);
    if (state.timeframe !== urlTf) nextParams.set("timeframe", state.timeframe);
    if (nextParams.toString() !== searchParams.toString()) {
      setSearchParams(nextParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, timeframe]);

  const { data, isLoading, error, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["klines", symbol, timeframe],
    queryFn: () => fetchKLines(symbol, timeframe, 500),
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: false,
    staleTime: 3000,
  });

  // Sync symbol/candles to global symbolContextStore
  useEffect(() => {
    if (!data || data.candles.length === 0) return;
    useSymbolContext.getState().setContext({
      symbol: data.symbol,
      timeframe: data.timeframe,
      candles: data.candles,
    });
  }, [data]);

  return (
    <div className="flex flex-col gap-5">
      {isLoading && <ChartSkeleton />}

      {error && (
        <ErrorState
          title={t("common.error")}
          description={(error as Error).message || "无法加载 K 线数据，请检查 API 连接"}
          action={
            <Button variant="primary" size="sm" leftIcon={<RefreshCw className="w-3.5 h-3.5" />} onClick={() => void refetch()}>
              {t("common.retry")}
            </Button>
          }
        />
      )}

      {data && data.candles.length > 0 && (
        <>
          {/* 统一指标管理面板 — 主图叠层 + 副图指标合在一张卡里，按 overlay 分两组 */}
          {prefs && (() => {
            const unifiedDefs = getUnifiedDefs();
            const editingDef = unifiedDefs.find((d) => d.id === editingId);
            // 8 个指标的默认 params（与 preferences.ts DEFAULT_PREFS 对齐）
            const defaultParamsFor = (id: string): Record<string, number | string | boolean> => {
              const map: Record<string, Record<string, number | string | boolean>> = {
                ma30: { length: 30 },
                boll: { length: 20, mult: 2.0 },
                rsi: { length: 14 },
                rsi6: { length: 6 },
                rsi24: { length: 24 },
                macd: { fast: 12, slow: 26, signal: 9 },
                kdj: { length: 9 },
                stoch: { k: 14, d: 3 },
              };
              return map[id] ?? {};
            };
            return (
              <>
                <Card className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-semibold text-text-primary">指标管理</span>
                    <span className="text-[11px] text-text-tertiary">
                      单击切换 · 右键 / 双击改参数
                    </span>
                  </div>
                  <IndicatorTogglePanel
                    prefs={prefs}
                    defs={unifiedDefs}
                    onChange={handleIndicatorToggle}
                    onEditParams={setEditingId}
                  />
                </Card>

                {editingDef && (
                  <IndicatorParamsModal
                    indicatorId={editingId}
                    label={editingDef.label}
                    pref={prefs.indicators[editingId!]}
                    defaultParams={defaultParamsFor(editingId!)}
                    onSave={handleSaveParams}
                    onClose={() => setEditingId(null)}
                  />
                )}
              </>
            );
          })()}

          <KlineChart
            key={`${data.symbol}-${data.timeframe}-${prefs ? JSON.stringify(prefs.indicators) : "loading"}`}
            candles={data.candles}
            symbol={data.symbol}
            timeframe={data.timeframe}
            dataUpdatedAt={dataUpdatedAt}
            onSymbolChange={setSymbol}
            onTimeframeChange={setTimeframe}
          />

          <AnalysisPanel />
          <TrendAnalysisPanel
            candles={data.candles}
            symbol={data.symbol}
            timeframe={data.timeframe}
          />
        </>
      )}

      {data && data.candles.length === 0 && (
        <Card>
          <CardBody className="flex flex-col items-center justify-center text-center py-16 gap-3">
            <div className="w-12 h-12 rounded-2xl bg-bg-tertiary flex items-center justify-center text-text-tertiary">
              <CandlestickChart className="w-5 h-5" />
            </div>
            <p className="text-sm text-text-secondary">{t("common.noData")}</p>
          </CardBody>
        </Card>
      )}

      {isFetching && !isLoading && data && (
        <p className="text-[11px] text-text-tertiary text-center tabular-nums">
          {data.candles.length} {t("kline.candleCount")}
        </p>
      )}
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonStatCard key={i} />
        ))}
      </div>
      <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden">
        <div className="flex items-end justify-between gap-3 p-5 border-b border-[rgba(255,240,220,0.06)]">
          <Skeleton variant="text" width="120px" height="24px" />
          <Skeleton variant="text" width="80px" height="20px" />
        </div>
        <Skeleton height="480px" className="rounded-none" variant="rectangular" />
      </div>
    </div>
  );
}
