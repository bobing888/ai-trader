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
  Copy,
  Download,
  Edit3,
  FileUp,
  Github,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
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
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

const SOURCE_LABELS: Record<string, string> = {
  manual: "自建",
  import: "导入",
  github: "GitHub",
  builtin: "内置",
};

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
  });

  const filtered = (strategies ?? []).filter((s) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q);
  });

  const selected = strategies?.find((s) => s.id === selectedId);

  return (
    <div className="space-y-4">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">策略管理</h1>
          <p className="text-xs text-text-tertiary mt-1">
            自建 / 克隆 / 导入 / 导出 / GitHub 同步
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Github className="w-3.5 h-3.5" />}
            onClick={() => syncMut.mutate()}
            disabled={syncMut.isPending || !syncStatus?.enabled}
            loading={syncMut.isPending}
          >
            同步 GitHub
          </Button>
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

      {/* Sync status banner */}
      {syncStatus && (
        <div className="rounded-xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] p-3 flex flex-wrap items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1.5 text-text-tertiary">
            <RefreshCw className="w-3 h-3" />
            GitHub 同步
          </span>
          <span className="text-text-secondary">
            已收录 <span className="font-semibold text-text-primary tabular-nums">{syncStatus.github_strategies_count}</span> 条
          </span>
          <span className="text-text-tertiary">·</span>
          <span className="text-text-tertiary">每 {syncStatus.interval_hours}h 自动 · 手动可触发</span>
          {syncMut.data && (
            <span className="text-bull">
              本次同步：新增 {syncMut.data.added} / 跳过 {syncMut.data.skipped}
            </span>
          )}
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
              {[["", "全部"], ["enabled", "已启用"], ["disabled", "已禁用"]].map(([v, l]) => (
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
              <li className="p-3"><Skeleton className="h-12 w-full" /></li>
            )}
            {error && (
              <li className="p-3"><ErrorState title={(error as Error).message} /></li>
            )}
            {!isLoading && filtered.length === 0 && (
              <li className="p-6 text-center text-text-tertiary text-xs">暂无策略</li>
            )}
            {filtered.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => { setSelectedId(s.id); setEditing(false); }}
                  className={cn(
                    "w-full text-left p-3 border-b border-[rgba(255,240,220,0.04)] hover:bg-bg-tertiary/40 transition-colors",
                    selectedId === s.id && "bg-accent/10",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-text-primary truncate">{s.name}</span>
                    <SourceBadge source={s.source} />
                  </div>
                  <p className="text-[10px] text-text-tertiary line-clamp-1 mt-0.5">
                    {s.description || "(无描述)"}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5 text-[10px] text-text-tertiary">
                    <span className={cn("w-1.5 h-1.5 rounded-full", s.status === "enabled" ? "bg-bull" : "bg-text-tertiary")} />
                    {s.status === "enabled" ? "已启用" : "已禁用"}
                    <span>· 权重 {s.weight}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {/* Detail panel */}
        <div className="rounded-2xl bg-bg-secondary border border-[rgba(255,240,220,0.06)] overflow-hidden min-h-[400px]">
          {!selected ? (
            <div className="p-12 text-center text-text-tertiary text-sm">
              选择一个策略查看详情，或点击「新建」开始
            </div>
          ) : editing ? (
            <StrategyEditor
              strategy={selected}
              onCancel={() => setEditing(false)}
              onSave={(payload) => updateMut.mutate({ id: selected.id, payload })}
              saving={updateMut.isPending}
            />
          ) : (
            <StrategyDetail
              strategy={selected}
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
          )}
        </div>
      </div>
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const label = source.startsWith("github:") ? "GitHub" : SOURCE_LABELS[source] ?? source;
  const tone =
    source === "manual" ? "bg-accent/15 text-accent"
    : source.startsWith("github:") ? "bg-bull/10 text-bull"
    : source === "import" ? "bg-warning/10 text-warning"
    : "bg-bg-tertiary text-text-tertiary";
  return (
    <span className={cn("text-[9px] px-1.5 py-0.5 rounded-md uppercase tracking-wider font-semibold shrink-0", tone)}>
      {label}
    </span>
  );
}

function StrategyDetail({
  strategy,
  onEdit,
  onDelete,
  onClone,
  onExport,
}: {
  strategy: Strategy;
  onEdit: () => void;
  onDelete: () => void;
  onClone: () => void;
  onExport: () => void;
}) {
  return (
    <div className="p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-text-primary truncate">{strategy.name}</h2>
            <SourceBadge source={strategy.source} />
          </div>
          <p className="text-xs text-text-tertiary mt-1">{strategy.description || "(无描述)"}</p>
          <p className="text-[10px] text-text-tertiary mt-1 tabular-nums">
            创建 {new Date(strategy.created_at).toLocaleString("zh-CN")} · 更新 {new Date(strategy.updated_at).toLocaleString("zh-CN")}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button variant="ghost" size="sm" leftIcon={<Edit3 className="w-3.5 h-3.5" />} onClick={onEdit}>编辑</Button>
          <Button variant="ghost" size="sm" leftIcon={<Copy className="w-3.5 h-3.5" />} onClick={onClone}>克隆</Button>
          <Button variant="ghost" size="sm" leftIcon={<Download className="w-3.5 h-3.5" />} onClick={onExport}>导出</Button>
          <Button variant="ghost" size="sm" leftIcon={<Trash2 className="w-3.5 h-3.5" />} onClick={onDelete}>删除</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Stat label="类型" value={strategy.strategy_type} />
        <Stat label="状态" value={strategy.status === "enabled" ? "已启用" : "已禁用"} />
        <Stat label="权重" value={strategy.weight.toFixed(2)} />
        <Stat label="参数数" value={Object.keys(strategy.parameters).length} />
      </div>

      <div>
        <h3 className="text-[10px] uppercase tracking-wider text-text-tertiary font-semibold mb-1.5">参数</h3>
        <pre className="rounded-lg bg-bg-tertiary p-3 text-[11px] font-mono text-text-primary overflow-x-auto">
          {Object.keys(strategy.parameters).length > 0
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
      <h2 className="text-sm font-medium text-text-primary mb-1">编辑策略</h2>
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
      <div className="flex items-center gap-2 pt-2">
        <Button variant="primary" type="submit" size="sm" leftIcon={<FileUp className="w-3.5 h-3.5" />} loading={saving}>
          保存
        </Button>
        <Button variant="ghost" type="button" size="sm" onClick={onCancel}>取消</Button>
      </div>
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

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-bg-tertiary px-3 py-2">
      <p className="text-[10px] text-text-tertiary uppercase tracking-wider">{label}</p>
      <p className="text-sm font-semibold tabular-nums mt-0.5 truncate">{value}</p>
    </div>
  );
}
