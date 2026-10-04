import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  Brain,
  ChevronDown,
  ChevronUp,
  Clock,
  PlayCircle,
  Shield,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import {
  fetchAgentRecommendations,
  fetchAgentReports,
  type AgentAnalysisReport,
  type AgentRecommendation,
  type AgentStatus,
} from "@/lib/api";

// === Constants ===

const ALLOWED_PAIRS = ["BTC-USDT", "ETH-USDT"] as const;
const ALLOWED_TIMEFRAMES = ["5m", "15m", "1h", "1d"] as const;

const REGIME_COLORS: Record<string, string> = {
  bull: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  bear: "text-rose-400 bg-rose-500/10 border-rose-500/30",
  choppy: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  neutral: "text-slate-400 bg-slate-500/10 border-slate-500/30",
  transition: "text-violet-400 bg-violet-500/10 border-violet-500/30",
};

const STATUS_COLORS: Record<AgentStatus, string> = {
  success: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  fallback: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  parse_error: "text-rose-400 bg-rose-500/10 border-rose-500/30",
  data_incomplete: "text-orange-400 bg-orange-500/10 border-orange-500/30",
};

const REGIME_LABELS: Record<string, string> = {
  bull: "多头",
  bear: "空头",
  choppy: "震荡",
  neutral: "中性",
  transition: "转换",
};

const STATUS_LABELS: Record<AgentStatus, string> = {
  success: "成功",
  fallback: "降级",
  parse_error: "解析失败",
  data_incomplete: "数据不全",
};

// === Helpers ===

function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function confidenceColor(c: number): string {
  if (c >= 0.7) return "text-emerald-400";
  if (c >= 0.5) return "text-amber-400";
  return "text-rose-400";
}

// === Components ===

function ReportCard({ report }: { report: AgentAnalysisReport }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="transition-all hover:border-violet-500/40">
      <CardBody>
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <span className="text-lg font-mono font-semibold">{report.pair}</span>
            <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
              {report.timeframe}
            </span>
            <span
              className={cn(
                "text-xs px-2 py-0.5 rounded border",
                REGIME_COLORS[report.regime] || "text-slate-400 bg-slate-500/10",
              )}
            >
              {REGIME_LABELS[report.regime] || report.regime}
              {" "}
              <span className="opacity-70">
                {(report.regime_confidence * 100).toFixed(0)}%
              </span>
            </span>
          </div>
          <span
            className={cn(
              "text-xs px-2 py-0.5 rounded border",
              STATUS_COLORS[report.analysis_status],
            )}
          >
            {STATUS_LABELS[report.analysis_status]}
          </span>
        </div>

        {/* Reasoning preview */}
        <p className="text-sm text-slate-300 line-clamp-2 mb-2">{report.reasoning}</p>

        {/* Footer: time + actions */}
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatTime(report.created_at)}
          </span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-violet-400 hover:text-violet-300 transition-colors"
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {expanded ? "收起" : "展开"}
          </button>
        </div>

        {/* Expanded details */}
        {expanded && (
          <div className="mt-3 pt-3 border-t border-slate-800 space-y-3">
            {report.key_observations && report.key_observations.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-slate-300 mb-1 flex items-center gap-1">
                  <Target className="h-3 w-3" />
                  关键观察
                </h4>
                <ul className="text-xs text-slate-400 space-y-0.5 list-disc list-inside">
                  {report.key_observations.map((o, i) => (
                    <li key={i}>{o}</li>
                  ))}
                </ul>
              </div>
            )}
            {report.risks && report.risks.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-rose-400 mb-1 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  风险
                </h4>
                <ul className="text-xs text-slate-400 space-y-0.5 list-disc list-inside">
                  {report.risks.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            <div>
              <span className="text-xs text-slate-500">置信度: </span>
              <span className={cn("text-xs font-mono", confidenceColor(report.regime_confidence))}>
                {(report.regime_confidence * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function RecommendationRow({ rec }: { rec: AgentRecommendation }) {
  const DirectionIcon =
    rec.direction === "long"
      ? TrendingUp
      : rec.direction === "short"
      ? TrendingDown
      : Activity;
  const dirColor =
    rec.direction === "long"
      ? "text-emerald-400"
      : rec.direction === "short"
      ? "text-rose-400"
      : "text-slate-400";

  return (
    <div className="grid grid-cols-12 items-center gap-2 px-4 py-3 border-b border-slate-800 last:border-0 hover:bg-slate-800/30 transition-colors">
      <div className="col-span-2 font-mono text-sm">{rec.pair}</div>
      <div className="col-span-1 text-xs text-slate-400">{rec.timeframe}</div>
      <div className={cn("col-span-2 flex items-center gap-1", dirColor)}>
        <DirectionIcon className="h-3.5 w-3.5" />
        <span className="text-xs uppercase font-semibold">{rec.direction}</span>
      </div>
      <div className="col-span-1">
        <span className={cn("text-sm font-mono", confidenceColor(rec.confidence))}>
          {(rec.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <div className="col-span-4 text-xs text-slate-400 truncate" title={rec.rationale}>
        {rec.rationale}
      </div>
      <div className="col-span-1 text-xs">
        <Badge tone={rec.source === "llm" ? "info" : "muted"}>{rec.source}</Badge>
      </div>
      <div className="col-span-1 text-xs text-slate-500 text-right">
        {formatTime(rec.created_at)}
      </div>
    </div>
  );
}

function PageHeader() {
  return (
    <div className="flex items-center justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Brain className="h-6 w-6 text-violet-400" />
          智能趋势研判
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          AI Agent 每 5 分钟分析 BTC/ETH × 4 时间维度 · 第二意见（不影响规则引擎）
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Badge tone="info" className="text-violet-300 border-violet-500/30">
          <Sparkles className="h-3 w-3 mr-1" />
          5m 循环
        </Badge>
        <Badge tone="warning" className="text-amber-300 border-amber-500/30">
          <Shield className="h-3 w-3 mr-1" />
          仅推荐
        </Badge>
      </div>
    </div>
  );
}

function Filters({
  pair,
  setPair,
  timeframe,
  setTimeframe,
}: {
  pair: string;
  setPair: (v: string) => void;
  timeframe: string;
  setTimeframe: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 mb-4">
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-400">交易对:</span>
        {ALLOWED_PAIRS.map((p) => (
          <button
            key={p}
            onClick={() => setPair(p)}
            className={cn(
              "px-3 py-1 text-xs rounded border transition-colors",
              pair === p
                ? "bg-violet-500/20 border-violet-500 text-violet-200"
                : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-600",
            )}
          >
            {p}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-400">时间维度:</span>
        {ALLOWED_TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf)}
            className={cn(
              "px-3 py-1 text-xs rounded border transition-colors",
              timeframe === tf
                ? "bg-violet-500/20 border-violet-500 text-violet-200"
                : "bg-slate-800/50 border-slate-700 text-slate-400 hover:border-slate-600",
            )}
          >
            {tf}
          </button>
        ))}
      </div>
    </div>
  );
}

export function TrendAgentPage() {
  const { t: _t } = useTranslation();
  const [pair, setPair] = useState<string>("BTC-USDT");
  const [timeframe, setTimeframe] = useState<string>("1h");

  // Reports query
  const reportsQuery = useQuery({
    queryKey: ["agent", "reports", pair, timeframe],
    queryFn: () => fetchAgentReports(pair, timeframe, 30),
    refetchInterval: 60_000,  // 1min
    staleTime: 30_000,
  });

  // Recommendations query
  const recsQuery = useQuery({
    queryKey: ["agent", "recommendations", pair, timeframe],
    queryFn: () => fetchAgentRecommendations(pair, timeframe, 20),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const reports = reportsQuery.data?.items ?? [];
  const recs = recsQuery.data?.items ?? [];

  // Summary stats
  const successCount = reports.filter((r) => r.analysis_status === "success").length;
  const fallbackCount = reports.filter((r) => r.analysis_status === "fallback").length;
  const totalCount = reports.length;

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">
      <PageHeader />

      {/* Summary bar */}
      <Card className="mb-6">
        <CardBody>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-slate-400">最近研判</div>
              <div className="text-2xl font-bold mt-1">{totalCount}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">LLM 成功</div>
              <div className="text-2xl font-bold text-emerald-400 mt-1">
                {successCount}
                <span className="text-xs text-slate-500 ml-1">
                  {totalCount > 0 ? `(${((successCount / totalCount) * 100).toFixed(0)}%)` : ""}
                </span>
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">降级运行</div>
              <div className="text-2xl font-bold text-amber-400 mt-1">{fallbackCount}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">推荐单</div>
              <div className="text-2xl font-bold text-violet-400 mt-1">{recs.length}</div>
            </div>
          </div>
        </CardBody>
      </Card>

      <Filters
        pair={pair}
        setPair={setPair}
        timeframe={timeframe}
        setTimeframe={setTimeframe}
      />

      {/* Reports list */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Zap className="h-4 w-4 text-violet-400" />
          最近研判
        </h2>
        {reportsQuery.isLoading ? (
          <div className="space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : reports.length === 0 ? (
          <EmptyState
            title="暂无研判数据"
            description="Agent 5 分钟循环尚未生成数据。检查 DEEPSEEK_API_KEY 是否配置。"
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {reports.map((r, i) => (
              <ReportCard key={`${r.pair}-${r.timeframe}-${i}-${r.created_at}`} report={r} />
            ))}
          </div>
        )}
      </div>

      {/* Recommendations table */}
      <div>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <PlayCircle className="h-4 w-4 text-violet-400" />
          推荐单（第二意见）
        </h2>
        {recsQuery.isLoading ? (
          <SkeletonCard />
        ) : recs.length === 0 ? (
          <EmptyState
            title="暂无推荐"
            description="Agent 尚未给出第二意见推荐。"
          />
        ) : (
          <Card>
            <div className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-slate-700 text-xs text-slate-400 uppercase">
              <div className="col-span-2">交易对</div>
              <div className="col-span-1">周期</div>
              <div className="col-span-2">方向</div>
              <div className="col-span-1">置信度</div>
              <div className="col-span-4">理由</div>
              <div className="col-span-1">来源</div>
              <div className="col-span-1 text-right">时间</div>
            </div>
            {recs.map((rec, i) => (
              <RecommendationRow key={`${rec.pair}-${rec.timeframe}-${i}-${rec.created_at}`} rec={rec} />
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}

export default TrendAgentPage;