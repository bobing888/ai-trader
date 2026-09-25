import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  CandlestickChart,
  Sparkles,
  Receipt,
  History,
  Settings as SettingsIcon,
  Sun,
  Moon,
  TrendingUp,
  TrendingDown,
  ArrowUp,
  ArrowDown,
} from "lucide-react";

import { useTheme } from "@/components/ui/ThemeToggle";
import { cn } from "@/lib/utils";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  group: "导航" | "主题" | "交易对";
  icon: React.ReactNode;
  action: () => void;
}

interface CommandPaletteValue {
  open: () => void;
  close: () => void;
  toggle: () => void;
}

const CommandPaletteContext = createContext<CommandPaletteValue | null>(null);

export function useCommandPalette(): CommandPaletteValue["open"] {
  const ctx = useContext(CommandPaletteContext);
  if (!ctx) {
    // Fallback no-op so consumers outside provider don't crash
    return () => {};
  }
  return ctx.open;
}

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const openFn = useCallback(() => setOpen(true), []);
  const closeFn = useCallback(() => setOpen(false), []);
  const toggleFn = useCallback(() => setOpen((p) => !p), []);

  // Global ⌘K / Ctrl+K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggleFn();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggleFn]);

  const value = useMemo(() => ({ open: openFn, close: closeFn, toggle: toggleFn }), [openFn, closeFn, toggleFn]);

  return (
    <CommandPaletteContext.Provider value={value}>
      {children}
      <CommandPalette open={open} onClose={closeFn} />
    </CommandPaletteContext.Provider>
  );
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const { theme, toggle: toggleTheme } = useTheme();

  if (!open) return null;

  // Hook called only when open (preserves hook order on parent re-render)
  return <CommandPaletteInner onClose={onClose} theme={theme} toggleTheme={toggleTheme} />;
}

interface CommandPaletteInnerProps {
  onClose: () => void;
  theme: "dark" | "light";
  toggleTheme: () => void;
}

function CommandPaletteInner({ onClose, theme, toggleTheme }: CommandPaletteInnerProps) {
  const [search, setSearch] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setSearch("");
    setActiveIndex(0);
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  const items: CommandItem[] = useMemo(() => {
    const navItems: CommandItem[] = [
      { id: "nav-kline", label: "K 线图", group: "导航", icon: <CandlestickChart className="w-4 h-4" />, action: () => navigate("/") },
      { id: "nav-rec", label: "推荐单", group: "导航", icon: <Sparkles className="w-4 h-4" />, action: () => navigate("/recommendations") },
      { id: "nav-trades", label: "交易记录", group: "导航", icon: <Receipt className="w-4 h-4" />, action: () => navigate("/trades") },
      { id: "nav-backtest", label: "回测复盘", group: "导航", icon: <History className="w-4 h-4" />, action: () => navigate("/backtest") },
      { id: "nav-settings", label: "设置", group: "导航", icon: <SettingsIcon className="w-4 h-4" />, action: () => navigate("/settings") },
    ];
    const themeItems: CommandItem[] = [
      {
        id: "theme-toggle",
        label: theme === "dark" ? "切换到浅色模式" : "切换到深色模式",
        hint: theme === "dark" ? "当前：深色" : "当前：浅色",
        group: "主题",
        icon: theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />,
        action: () => toggleTheme(),
      },
    ];
    const pairItems: CommandItem[] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"].map((p) => ({
      id: `pair-${p}`,
      label: p,
      hint: `切换到 ${p}`,
      group: "交易对" as const,
      icon: p.includes("BTC") ? <TrendingUp className="w-4 h-4 text-warning" />
        : p.includes("ETH") ? <TrendingUp className="w-4 h-4 text-info" />
        : p.includes("SOL") ? <TrendingDown className="w-4 h-4 text-bull" />
        : <TrendingUp className="w-4 h-4 text-warning" />,
      action: () => navigate(`/?symbol=${p}`),
    }));
    return [...navItems, ...themeItems, ...pairItems];
  }, [navigate, theme, toggleTheme]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (it) => it.label.toLowerCase().includes(q) || it.hint?.toLowerCase().includes(q),
    );
  }, [items, search]);

  useEffect(() => {
    setActiveIndex(0);
  }, [search]);

  // Keyboard nav
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((p) => Math.min(p + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((p) => Math.max(p - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const item = filtered[activeIndex];
        if (item) {
          item.action();
          onClose();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, filtered, activeIndex, onClose]);

  if (!open) return null;

  const groups = filtered.reduce((acc, it) => {
    if (!acc[it.group]) acc[it.group] = [];
    acc[it.group].push(it);
    return acc;
  }, {} as Record<string, CommandItem[]>);

  let runningIndex = -1;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-start justify-center pt-[10vh] px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-[fade-in_0.15s_ease-out]"
        onClick={onClose}
      />
      <div
        className={cn(
          "relative w-full max-w-lg rounded-2xl",
          "bg-bg-secondary border border-[rgba(255,240,220,0.12)]",
          "shadow-2xl shadow-black/60 overflow-hidden",
          "animate-[slide-up-fade_0.2s_cubic-bezier(0.16,1,0.3,1)]",
        )}
      >
        {/* Search input */}
        <div className="flex items-center gap-2 px-4 h-14 border-b border-[rgba(255,240,220,0.06)]">
          <Search className="w-4 h-4 text-text-tertiary shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="输入命令或搜索…"
            data-testid="command-palette-input"
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none"
          />
          <kbd className="hidden sm:inline-flex h-5 px-1.5 items-center rounded-md bg-bg-tertiary border border-[rgba(255,240,220,0.06)] text-[10px] font-medium text-text-tertiary">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[60vh] overflow-y-auto p-2">
          {filtered.length === 0 && (
            <div className="px-4 py-12 text-center text-sm text-text-tertiary">
              没有匹配的命令
            </div>
          )}
          {Object.entries(groups).map(([groupName, groupItems]) => (
            <div key={groupName} className="mb-1.5 last:mb-0">
              <div className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-text-tertiary">
                {groupName}
              </div>
              {groupItems.map((it) => {
                runningIndex++;
                const isActive = runningIndex === activeIndex;
                const currentIdx = runningIndex;
                return (
                  <button
                    key={it.id}
                    onMouseEnter={() => setActiveIndex(currentIdx)}
                    onClick={() => {
                      it.action();
                      onClose();
                    }}
                    data-testid={`cmd-${it.id}`}
                    className={cn(
                      "w-full flex items-center gap-3 h-10 px-3 rounded-xl text-left transition-colors",
                      isActive ? "bg-bg-tertiary" : "bg-transparent",
                    )}
                  >
                    <span
                      className={cn(
                        "shrink-0 w-7 h-7 rounded-lg flex items-center justify-center",
                        isActive ? "bg-accent/15 text-accent" : "bg-bg-tertiary text-text-secondary",
                      )}
                    >
                      {it.icon}
                    </span>
                    <span className="flex-1 text-sm font-medium text-text-primary">{it.label}</span>
                    {it.hint && (
                      <span className="text-[11px] text-text-tertiary tabular-nums">{it.hint}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 h-9 border-t border-[rgba(255,240,220,0.06)] text-[10px] text-text-tertiary">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <ArrowUp className="w-3 h-3" />
              <ArrowDown className="w-3 h-3" />
              导航
            </span>
            <span className="flex items-center gap-1">
              <kbd className="h-4 px-1 rounded bg-bg-tertiary border border-[rgba(255,240,220,0.06)]">↵</kbd>
              选中
            </span>
          </div>
          <span>AI 交易助手 · ⌘K</span>
        </div>
      </div>
    </div>
  );
}
