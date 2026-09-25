/**
 * 全局 Right Sidebar — 跨页面可见的可折叠抽屉。
 * 默认内容：合约交易计算器。未来可扩展其他工具。
 */

import { useState, type ReactNode } from "react";
import { ChevronLeft, Repeat, X } from "lucide-react";

import { FuturesContractPanel } from "@/components/FuturesContractPanel";
import { cn } from "@/lib/utils";

const SIDEBAR_KEY = "right-sidebar-collapsed";

function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

export function RightSidebar() {
  const [collapsed, setCollapsed] = useState<boolean>(getInitialCollapsed);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  return (
    <aside
      className={cn(
        "hidden xl:flex h-full shrink-0 flex-col border-l border-[rgba(255,240,220,0.06)] bg-bg-secondary/40 transition-[width] duration-300 ease-in-out",
        collapsed ? "w-12" : "w-[360px]",
      )}
      aria-label="工具侧边栏"
    >
      <div className="flex items-center justify-between gap-2 px-3 py-3 border-b border-[rgba(255,240,220,0.06)]">
        {!collapsed && (
          <div className="flex items-center gap-2 min-w-0">
            <Repeat className="w-3.5 h-3.5 text-text-tertiary shrink-0" />
            <h2 className="text-xs font-semibold text-text-primary uppercase tracking-wider truncate">
              工具
            </h2>
          </div>
        )}
        <div className="flex items-center gap-1 ml-auto">
          <button
            onClick={toggle}
            className="w-7 h-7 rounded-md flex items-center justify-center text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
            aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
            title={collapsed ? "展开侧边栏" : "收起侧边栏"}
          >
            {collapsed ? <ChevronLeft className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          <Section title="合约计算器" hint="基于 K 线自动算仓位与爆仓">
            <FuturesContractPanel />
          </Section>
        </div>
      )}
    </aside>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-[rgba(255,240,220,0.06)] bg-bg-secondary/60">
      <header className="px-4 py-2.5 border-b border-[rgba(255,240,220,0.06)] flex items-center justify-between">
        <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider">{title}</h3>
        {hint && <span className="text-[10px] text-text-tertiary">{hint}</span>}
      </header>
      <div>{children}</div>
    </section>
  );
}
