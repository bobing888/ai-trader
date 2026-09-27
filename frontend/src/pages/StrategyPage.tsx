/**
 * StrategyPage — 策略管理（CRUD + GitHub 同步 + 导入/导出）
 *
 * 三个区域：
 *   1. 顶部：搜索 + 过滤 + 新建 + 同步 GitHub 按钮
 *   2. 左侧：策略列表
 *   3. 右侧：详情 / 编辑 / 代码预览
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Download,
  Edit3,
  FileUp,
  Github,
  Plus,
  Search,
  Trash2,
  Upload,
  Zap,
} from "lucide-react";
import { useRef, useState } from "react";

import {
  cloneStrategy,
  createStrategy,
  deleteStrategy,
  exportStrategy,
  fetchGithubSyncStatus,
  fetchStrategies,
  importStrategy,
  STRATEGY_TYPES,
  triggerGithubSync,
  updateStrategy,
  type Strategy,
  type StrategyCreate,
} from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

// ─── Constants ────────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  manual: "自建",
  import: "导入",
  github: "GitHub",
  builtin: "内置",
};

const STRATEGY_TYPE_COLORS: Record<string, "bull" | "bear" | "warning" | "info" | "accent" | "default"> = {
  trend: "bull",
  mean_reversion: "bear",
  momentum: "warning",
  volatility: "info",
  volume: "accent",
  custom: "default",
};

const STATUS_CONFIG: Record<string, { label: string; tone: "bull" | "bear" | "warning" | "muted" }> = {
  enabled: { label: "已启用", tone: "bull" },
  disabled: { label: "已禁用", tone: "muted" },
  draft: { label: "草稿", tone: "warning" },
  error: { label: "错误", tone: "bear" },
};

// ─── Relative time helper ─────────────────────────────────────────────────────

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Date(dateStr).toLocaleDateString("zh-CN");
}

function codeLineCount(code: string): number {
  return code ? code.split("\n").length : 0;
}

// ─── Sync status badge (used in header + detail page) ─────────────────────────

type SyncState = "idle" | "syncing" | "success" | "failed";

function getSyncState(
  syncPending: boolean,
  lastSyncAt: string | undefined,
  lastError: string | undefined,
): SyncState {
  if (syncPending) return "syncing";
  if (lastError) return "failed";
  if (lastSyncAt) return "success";
  return "idle";
}

function SyncStatusButton({
  syncPending,
  lastSyncAt,
  lastError,
  onSync,
  disabled,
}: {
  syncPending: boolean;
  lastSyncAt?: string;
  lastError?: string;
  onSync: () => void;
  disabled: boolean;
}) {
  const state = getSyncState(syncPending, lastSyncAt, lastError);

  if (state === "success") {
    return (
      <Button
        variant="secondary"
        size="sm"
        leftIcon={<CheckCircle2 className="w-3.5 h-3.5 text-bull" />}
        className="text-bull border-bull/20"
        onClick={onSync}
        disabled={syncPending || disabled}
        loading={syncPending}
      >
        已同步 {lastSyncAt ? relativeTime(lastSyncAt) : ""}
      </Button>
    );
  }

  if (state === "failed") {
    return (
      <div className="group relative">
        <Button
          variant="secondary"
          size="sm"
          leftIcon={<AlertTriangle className="w-3.5 h-3.5 text-bear" />}
          className="text-bear border-bear/20"
          onClick={onSync}
          disabled={syncPending || disabled}
          loading={syncPending}
        >
          同步失败
        </Button>
        {lastError && (
          <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10 w-64 rounded-lg bg-bg-secondary border border-bear/25 px-3 py-2 text-[11px] text-text-secondary shadow-xl">
            {lastError}
          </div>
        )}
      </div>
    );
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      leftIcon={<Github className="w-3.5 h-3.5" />}
      onClick={onSync}
      disabled={syncPending || disabled}
      loading={syncPending}
    >
      {syncPending ? "同步中..." : "同步 GitHub"}
    </Button>
  );
}

// ─── Badge helpers ─────────────────────────────────────────────────────────────

function TypeBadge({ type }: { type: string }) {
  const tone = STRATEGY_TYPE_COLORS[type] ?? "default";
  return (
    <Badge tone={tone} className="text-[10px]">
      {type}
    </Badge>
  );
}

function SourceBadge({ source }: { source: string }) {
  const isGithub = source.startsWith("github:");
  const label = isGithub ? "GitHub" : SOURCE_LABELS[source] ?? source;
  const tone = isGithub ? "info" : source === "manual" ? "accent" : source === "import" ? "warning" : "muted";
  return (
    <Badge tone={tone} className="text-[10px]">
      {label}
    </Badge>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, tone: "muted" as const };
  return <Badge tone={cfg.tone} className="text-[10px]">{cfg.label}</Badge>;
}

// ─── Main component ───────────────────────────────────────────────────────────

export function StrategyPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editing, setEditing] = useState<boolean>(false);
  const [search, setSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: strategies, isLoading, error } = useQuery({
    queryKey: ["strategies", statusFilter],
    queryFn: () => fetchStrategies({ status: statusFilter || undefined, limit: 100 }),
  });

  const { data: syncStatus } = useQuery({
    queryKey: ["github-sync-status"],
    queryFn: fetchGithubSyncStatus,
    refetchInterval: 30_000,
  });

  const createMut = useMutation({
    mutationFn: (p: StrategyCreate) => createStrategy(p),
    onSuccess: (s) => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setSelectedId(s.id);
      setEditing(false);
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Parameters<typeof updateStrategy>[1] }) =>
      updateStrategy(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setEditing(false);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteStrategy(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setSelectedId(null);
    },
  });

  const cloneMut = useMutation({
    mutationFn: (id: number) => cloneStrategy(id),
    onSuccess: (s) => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      setSelectedId(s.id);
    },
  });

  const syncMut = useMutation({
    mutationFn: () => triggerGithubSync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      queryClient.invalidateQueries({ queryKey: ["github-sync-status"] });
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ["github-sync-status"] });
    },
  });

  const filtered = (strategies ?? []).filter((s) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q);
  });

  const selected = strategies?.find((s) => s.id === selectedId);

  // Summary stats
  const enabledCount = (strategies ?? []).filter((s) => s.status === "enabled").length;
  const disabledCount = (strategies ?? []).filter((s) => s.status === "disabled").length;
  const githubCount = syncStatus?.github_strategies_count ?? 0;

  return (
    <div className="space-y-4">
      {/* Header */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">策略管理</h1>
          <p className="text-xs text-text-tertiary mt-1">
            自建 / 克隆 / 导入 / 导出 / GitHub 同步
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SyncStatusButton
            syncPending={syncMut.isPending}
            lastSyncAt={syncMut.data?.synced_at}
            lastError={syncMut.data?.error}
            onSync={() => syncMut.mutate()}
            disabled={!syncStatus?.enabled}
          />
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Upload className="w-3.5 h-3.5" />}
            onClick={() => fileInputRef.current?.click()}
          >
            导入 JSON
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              try {
                const text = await f.text();
                const payload = JSON.parse(text);
                const created = await importStrategy(payload);
                queryClient.invalidateQueries({ queryKey: ["strategies"] });
                setSelectedId(created.id);
              } catch (err) {
                alert(`导入失败: ${(err as Error).message}`);
              } finally {
                e.target.value = "";
              }
            }}
          />
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
            onClick={() => {
              const name = window.prompt("策略名称");
              if (!name) return;
              createMut.mutate({ name, description: "", parameters: {}, code: "" });
            }}
          >
            新建
          </Button>
        </div>
      </header>

      {/* Page summary bar */}
      {!isLoading && (
        <div className="flex flex-wrap items-center gap-4 rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.08)] px-4 py-2.5 text-xs">
          <div className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-accent" />
            <span className="text-text-secondary">策略总数</span>
            <span className="font-semibold text-text-primary tabular-nums">
              {(strategies ?? []).length}
            </span>
          </div>
          <div className="w-px h-3.5 bg-[rgba(255,240,220,0.08)]" />
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-bull" />
            <span className="text-text-secondary">启用</span>
            <span className="font-semibold text-bull tabular-nums">{enabledCount}</span>
          </div>
          <div className="w-px h-3.5 bg-[rgba(255,240,220,0.08)]" />
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-text-tertiary" />
            <span className="text-text-secondary">禁用</span>
            <span className="font-semibold text-text-secondary tabular-nums">{disabledCount}</span>
          </div>
          <div className="w-px h-3.5 bg-[rgba(255,240,220,0.08)]" />
          <div className="flex items-center gap-1.5">
            <Github className="w-3.5 h-3.5 text-info" />
            <span className="text-text-secondary">GitHub</span>
            <span className="font-semibold text-info tabular-nums">{githubCount}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
        {/* List panel */}
        <aside className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden">
          <div className="p-3 space-y-2 border-b border-[rgba(255,240,220,0.06)]">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索策略..."
                className="w-full h-8 pl-8 pr-2 rounded-md bg-bg-tertiary text-sm placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div className="flex items-center gap-1.5 text-[10px]">
              {([["", "全部"], ["enabled", "已启用"], ["disabled", "已禁用"]] as const).map(([v, l]) => (
                <button
                  key={v}
                  onClick={() => setStatusFilter(v)}
                  className={cn(
                    "h-6 px-2 rounded-md transition-colors",
                    statusFilter === v ? "bg-accent/20 text-accent" : "bg-bg-tertiary text-text-tertiary hover:text-text-primary",
                  )}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>

          <ul className="max-h-[60vh] overflow-y-auto">
            {isLoading && (
              <>
                {Array.from({ length: 4 }).map((_, i) => (
                  <li key={i} className="p-3 border-b border-[rgba(255,240,220,0.04)]">
                    <Skeleton className="h-14 w-full" />
                  </li>
                ))}
              </>
            )}
            {error && (
              <li className="p-3">
                <ErrorState title={(error as Error).message} />
              </li>
            )}
            {!isLoading && filtered.length === 0 && !error && (
              <li className="p-6">
                <EmptyState
                  icon={<Zap className="w-5 h-5" />}
                  title="还没有策略"
                  description="创建一个策略或从 GitHub 同步，开始你的量化之旅"
                  action={
                    <Button
                      variant="primary"
                      size="sm"
                      leftIcon={<Plus className="w-3.5 h-3.5" />}
                      onClick={() => {
                        const name = window.prompt("策略名称");
                        if (!name) return;
                        createMut.mutate({ name, description: "", parameters: {}, code: "" });
                      }}
                    >
                      创建第一个策略
                    </Button>
                  }
                />
              </li>
            )}
            {filtered.map((s) => (
              <li key={s.id}>
                <StrategyListItem
                  strategy={s}
                  selected={selectedId === s.id}
                  onClick={() => { setSelectedId(s.id); setEditing(false); }}
                />
              </li>
            ))}
          </ul>
        </aside>

        {/* Detail panel */}
        <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden min-h-[400px]">
          {!selected && !isLoading ? (
            <div className="flex items-center justify-center h-full min-h-[300px]">
              <EmptyState
                icon={<Zap className="w-6 h-6" />}
                title="选择一个策略"
                description="从左侧列表选择一个策略查看详情，或点击「新建」开始"
              />
            </div>
          ) : isLoading ? (
            <div className="p-6 space-y-4">
              <Skeleton className="h-8 w-48" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : selected && editing ? (
            <StrategyEditor
              strategy={selected}
              onCancel={() => setEditing(false)}
              onSave={(payload) => updateMut.mutate({ id: selected.id, payload })}
              saving={updateMut.isPending}
            />
          ) : selected ? (
            <StrategyDetail
              strategy={selected}
              syncPending={syncMut.isPending}
              lastSyncAt={syncMut.data?.synced_at}
              lastSyncError={syncMut.data?.error}
              syncEnabled={!!syncStatus?.enabled}
              onSync={() => syncMut.mutate()}
              onEdit={() => setEditing(true)}
              onDelete={() => {
                if (window.confirm(`确认删除「${selected.name}」？`)) {
                  deleteMut.mutate(selected.id);
                }
              }}
              onClone={() => cloneMut.mutate(selected.id)}
              onExport={async () => {
                try {
                  const data = await exportStrategy(selected.id);
                  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `${selected.name.replace(/[^a-zA-Z0-9_-]/g, "_")}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                } catch (err) {
                  alert(`导出失败: ${(err as Error).message}`);
                }
              }}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ─── Strategy list item ───────────────────────────────────────────────────────

function StrategyListItem({
  strategy,
  selected,
  onClick,
}: {
  strategy: Strategy;
  selected: boolean;
  onClick: () => void;
}) {
  const paramCount = Object.keys(strategy.parameters ?? {}).length;

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left p-3 border-b border-[rgba(255,240,220,0.04)] hover:bg-bg-tertiary/40 transition-colors",
        selected && "bg-accent/10",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-text-primary truncate">{strategy.name}</span>
        <SourceBadge source={strategy.source} />
      </div>
      <p className="text-[10px] text-text-tertiary line-clamp-1 mt-0.5">
        {strategy.description || "(无描述)"}
      </p>
      {/* 4 badges row */}
      <div className="flex flex-wrap items-center gap-1 mt-1.5">
        <TypeBadge type={strategy.strategy_type} />
        <StatusBadge status={strategy.status} />
        {paramCount > 0 && (
          <span className="text-[9px] text-text-tertiary px-1.5 py-0.5 rounded-full bg-bg-tertiary">
            {paramCount} 个参数
          </span>
        )}
      </div>
    </button>
  );
}

// ─── Strategy detail ──────────────────────────────────────────────────────────

function StrategyDetail({
  strategy,
  syncPending,
  lastSyncAt,
  lastSyncError,
  syncEnabled,
  onSync,
  onEdit,
  onDelete,
  onClone,
  onExport,
}: {
  strategy: Strategy;
  syncPending: boolean;
  lastSyncAt?: string;
  lastSyncError?: string;
  syncEnabled: boolean;
  onSync: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onClone: () => void;
  onExport: () => void;
}) {
  const paramCount = Object.keys(strategy.parameters ?? {}).length;
  const lines = codeLineCount(strategy.code);
  const isGithub = strategy.source.startsWith("github:");

  return (
    <div className="p-5 space-y-4">
      {/* Header row: title + badges + actions */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h2 className="text-lg font-semibold text-text-primary truncate">{strategy.name}</h2>
            <TypeBadge type={strategy.strategy_type} />
            <SourceBadge source={strategy.source} />
            <StatusBadge status={strategy.status} />
          </div>
          <p className="text-xs text-text-tertiary">{strategy.description || "(无描述)"}</p>
        </div>

        {/* Action group — right side */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Edit group */}
          <Button variant="ghost" size="sm" leftIcon={<Edit3 className="w-3.5 h-3.5" />} onClick={onEdit}>
            编辑
          </Button>
          <div className="w-px h-4 bg-[rgba(255,240,220,0.08)] mx-0.5" />
          {/* Copy group */}
          <Button variant="ghost" size="sm" leftIcon={<Copy className="w-3.5 h-3.5" />} onClick={onClone}>
            克隆
          </Button>
          <Button variant="ghost" size="sm" leftIcon={<Download className="w-3.5 h-3.5" />} onClick={onExport}>
            导出
          </Button>
          <div className="w-px h-4 bg-[rgba(255,240,220,0.08)] mx-0.5" />
          {/* Danger group */}
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<Trash2 className="w-3.5 h-3.5" />}
            className="text-bear hover:text-bear hover:bg-bear/10"
            onClick={onDelete}
          >
            删除
          </Button>
        </div>
      </div>

      {/* Danger warning */}
      <div className="flex items-center gap-1.5 text-[10px] text-bear/70">
        <AlertTriangle className="w-3 h-3" />
        删除不可恢复
      </div>

      {/* Strategy overview card */}
      <div className="rounded-xl bg-bg-tertiary/50 border border-[rgba(255,240,220,0.06)] p-3 space-y-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px]">
          <div className="flex items-center gap-1.5 text-text-tertiary">
            <span>创建</span>
            <span className="text-text-secondary font-medium">{relativeTime(strategy.created_at)}</span>
          </div>
          <div className="w-px h-3 bg-[rgba(255,240,220,0.06)]" />
          <div className="flex items-center gap-1.5 text-text-tertiary">
            <span>更新</span>
            <span className="text-text-secondary font-medium">{relativeTime(strategy.updated_at)}</span>
          </div>
          <div className="w-px h-3 bg-[rgba(255,240,220,0.06)]" />
          <div className="flex items-center gap-1.5 text-text-tertiary">
            <span>代码</span>
            <span className="text-text-secondary font-medium tabular-nums">{lines} 行</span>
          </div>
          <div className="w-px h-3 bg-[rgba(255,240,220,0.06)]" />
          <div className="flex items-center gap-1.5 text-text-tertiary">
            <span>参数</span>
            <span className="text-text-secondary font-medium tabular-nums">{paramCount} 个</span>
          </div>
          {isGithub && (
            <>
              <div className="w-px h-3 bg-[rgba(255,240,220,0.06)]" />
              <div className="flex items-center gap-1.5 text-text-tertiary">
                <Github className="w-3 h-3" />
                <span className="text-info font-medium truncate max-w-[200px]">
                  {strategy.source.replace("github:", "")}
                </span>
              </div>
            </>
          )}
        </div>

        {/* GitHub sync status inline */}
        <div className="flex items-center gap-2 pt-1.5 border-t border-[rgba(255,240,220,0.06)]">
          <span className="text-[10px] text-text-tertiary">GitHub 同步</span>
          <SyncStatusButton
            syncPending={syncPending}
            lastSyncAt={lastSyncAt}
            lastError={lastSyncError}
            onSync={onSync}
            disabled={!syncEnabled}
          />
        </div>
      </div>

      <div>
        <h3 className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-1.5">参数</h3>
        <pre className="rounded-lg bg-bg-tertiary p-3 text-[11px] font-mono text-text-primary overflow-x-auto">
          {paramCount > 0
            ? JSON.stringify(strategy.parameters, null, 2)
            : "(无参数)"}
        </pre>
      </div>

      <div>
        <h3 className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-1.5">代码</h3>
        <pre className="rounded-lg bg-bg-tertiary p-3 text-[11px] font-mono text-text-primary overflow-x-auto max-h-96">
          {strategy.code || "(无代码)"}
        </pre>
      </div>
    </div>
  );
}

// ─── Strategy editor ──────────────────────────────────────────────────────────

function StrategyEditor({
  strategy,
  onCancel,
  onSave,
  saving,
}: {
  strategy: Strategy;
  onCancel: () => void;
  onSave: (p: Parameters<typeof updateStrategy>[1]) => void;
  saving: boolean;
}) {
  const [name, setName] = useState(strategy.name);
  const [description, setDescription] = useState(strategy.description);
  const [strategyType, setStrategyType] = useState(strategy.strategy_type);
  const [code, setCode] = useState(strategy.code);
  const [weight, setWeight] = useState(strategy.weight);
  const [status, setStatus] = useState(strategy.status);
  const [paramsText, setParamsText] = useState(JSON.stringify(strategy.parameters, null, 2));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        let params: Record<string, unknown> = {};
        try {
          params = paramsText.trim() ? JSON.parse(paramsText) : {};
        } catch (err) {
          alert(`参数 JSON 解析失败: ${(err as Error).message}`);
          return;
        }
        onSave({ name, description, strategy_type: strategyType, code, weight, status, parameters: params });
      }}
      className="p-5 space-y-3"
    >
      {/* Header + save/cancel group */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-primary">编辑策略</h2>
        <div className="flex items-center gap-2">
          <Button variant="primary" type="submit" size="sm" leftIcon={<FileUp className="w-3.5 h-3.5" />} loading={saving}>
            保存
          </Button>
          <Button variant="ghost" type="button" size="sm" onClick={onCancel}>
            取消
          </Button>
        </div>
      </div>

      <Field label="名称">
        <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} required />
      </Field>
      <Field label="描述">
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} className={`${inputCls} h-20 resize-none`} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="类型">
          <select value={strategyType} onChange={(e) => setStrategyType(e.target.value)} className={inputCls}>
            {STRATEGY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="状态">
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputCls}>
            <option value="enabled">enabled</option>
            <option value="disabled">disabled</option>
          </select>
        </Field>
      </div>
      <Field label="权重">
        <input type="number" step="0.1" min="0" value={weight} onChange={(e) => setWeight(parseFloat(e.target.value) || 0)} className={inputCls} />
      </Field>
      <Field label="参数 (JSON)">
        <textarea value={paramsText} onChange={(e) => setParamsText(e.target.value)} className={`${inputCls} h-24 font-mono text-[11px]`} />
      </Field>
      <Field label="代码">
        <textarea value={code} onChange={(e) => setCode(e.target.value)} className={`${inputCls} h-64 font-mono text-[11px]`} />
      </Field>
    </form>
  );
}

const inputCls =
  "w-full h-9 px-3 rounded-md bg-bg-tertiary text-sm focus:outline-none focus:ring-1 focus:ring-accent";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-1">{label}</span>
      {children}
    </label>
  );
}
