import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  CandlestickChart,
  Sparkles,
  Receipt,
  History,
  Brain,
  Repeat,
  Settings as SettingsIcon,
  X,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { fetchTradesSummary } from "@/lib/api";

interface SidebarProps {
  onClose?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function Sidebar({ onClose, collapsed = false, onToggleCollapse }: SidebarProps) {
  const { t } = useTranslation();

  const { data: summary } = useQuery({
    queryKey: ["trades-summary", "sidebar"],
    queryFn: fetchTradesSummary,
    refetchInterval: 30_000,
  });
  const openTradeCount = summary
    ? Math.max(0, summary.total_trades - summary.winning_trades - summary.losing_trades)
    : null;

  return (
    <aside className="w-full h-full bg-bg-secondary border-r border-[rgba(255,240,220,0.06)] flex flex-col relative">
      {/* Header */}
      <div className="h-16 flex items-center">
        {collapsed ? (
          /* Collapsed: centered logo */
          <div className="w-full flex justify-center">
            <div className="relative w-9 h-9 rounded-2xl bg-accent flex items-center justify-center shadow-[0_0_0_1px_rgba(204,255,0,0.5),0_4px_20px_-4px_rgba(204,255,0,0.45)]">
              <CandlestickChart className="w-4.5 h-4.5 text-[#140c0c]" strokeWidth={2.5} />
            </div>
          </div>
        ) : (
          /* Expanded: logo + toggle */
          <>
            <div className="flex items-center gap-2.5 px-5 flex-1 min-w-0">
              <div className="relative w-9 h-9 rounded-2xl bg-accent flex items-center justify-center shadow-[0_0_0_1px_rgba(204,255,0,0.5),0_4px_20px_-4px_rgba(204,255,0,0.45)] shrink-0">
                <CandlestickChart className="w-4.5 h-4.5 text-[#140c0c]" strokeWidth={2.5} />
              </div>
              <div className="flex flex-col leading-none overflow-hidden">
                <span className="text-[15px] font-semibold tracking-tight text-text-primary truncate">
                  {t("common.appName")}
                </span>
                <span className="text-[10px] font-medium tracking-wider uppercase text-text-tertiary mt-0.5">
                  {t("common.appTagline")}
                </span>
              </div>
            </div>
            {onToggleCollapse && (
              <button
                onClick={onToggleCollapse}
                className="p-2 mr-2 rounded-full text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
                aria-label="收起侧边栏"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            )}
            {onClose && (
              <button
                onClick={onClose}
                className="p-1.5 rounded-full text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors lg:hidden"
                aria-label="Close menu"
              >
                <X className="w-4.5 h-4.5" />
              </button>
            )}
          </>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto">
        <div className={cn("py-2 overflow-hidden", collapsed ? "px-1" : "px-3")}>
          <div className={cn("space-y-1", collapsed ? "flex flex-col items-center" : "")}>
            <SidebarNavItem to="/" testId="nav-kline" icon={CandlestickChart} end collapsed={collapsed}>
              {t("nav.kline")}
            </SidebarNavItem>
            <SidebarNavItem
              to="/recommendations"
              testId="nav-rec"
              icon={Sparkles}
              badge="新"
              collapsed={collapsed}
            >
              {t("nav.recommendations")}
            </SidebarNavItem>
            <SidebarNavItem
              to="/trades"
              testId="nav-trades"
              icon={Receipt}
              badge={openTradeCount !== null && openTradeCount > 0 ? String(openTradeCount) : null}
              collapsed={collapsed}
            >
              {t("nav.trades")}
            </SidebarNavItem>
            <SidebarNavItem to="/backtest" testId="nav-backtest" icon={History} collapsed={collapsed}>
              {t("nav.backtest")}
            </SidebarNavItem>
            <SidebarNavItem to="/strategies" testId="nav-strategies" icon={Brain} collapsed={collapsed}>
              {t("nav.strategies")}
            </SidebarNavItem>
            <SidebarNavItem to="/futures" testId="nav-futures" icon={Repeat} collapsed={collapsed}>
              {t("nav.futures")}
            </SidebarNavItem>
          </div>

          <div className={cn("pt-5 border-t border-[rgba(255,240,220,0.06)]", collapsed ? "w-full px-1" : "")}>
            {!collapsed && (
              <div className="px-3 mb-2">
                <span className="text-[10px] font-semibold tracking-wider uppercase text-text-tertiary">
                  {t("nav.system")}
                </span>
              </div>
            )}
            <div className={cn("space-y-1", collapsed ? "flex flex-col items-center" : "")}>
              <SidebarNavItem to="/settings" testId="nav-settings" icon={SettingsIcon} collapsed={collapsed}>
                {t("nav.settings")}
              </SidebarNavItem>
            </div>
          </div>
        </div>
      </nav>

      {/* Footer */}
      <div className={cn("border-t border-[rgba(255,240,220,0.06)]", collapsed ? "p-2" : "p-4")}>
        {collapsed ? (
          <div className="flex justify-center">
            <div className="flex flex-col items-center gap-1">
              <span className="relative flex w-2 h-2">
                <span className="absolute inline-flex w-full h-full rounded-full bg-bull opacity-50 animate-pulse-live" />
                <span className="relative inline-flex w-2 h-2 rounded-full bg-bull" />
              </span>
              <span className="text-[9px] text-text-tertiary">v0.1</span>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3 py-2 rounded-full bg-bg-tertiary border border-[rgba(255,240,220,0.06)]">
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex w-full h-full rounded-full bg-bull opacity-50 animate-pulse-live" />
              <span className="relative inline-flex w-2 h-2 rounded-full bg-bull" />
            </span>
            <span className="text-[11px] font-medium text-text-secondary">
              {t("common.liveFeed")}
            </span>
            <span className="ml-auto text-[10px] text-text-tertiary tabular-nums">v0.1.0</span>
          </div>
        )}
      </div>
    </aside>
  );
}

interface SidebarNavItemProps {
  to: string;
  testId: string;
  icon: LucideIcon;
  end?: boolean;
  badge?: string | null;
  collapsed?: boolean;
  children: ReactNode;
}

function SidebarNavItem({
  to,
  testId,
  icon: Icon,
  end,
  badge,
  collapsed = false,
  children,
}: SidebarNavItemProps) {
  const baseClass =
    "flex items-center h-10 rounded-full transition-all duration-150 cursor-pointer active:scale-[0.98]";

  return (
    <NavLink
      to={to}
      end={end}
      data-testid={testId}
      title={collapsed ? String(children) : undefined}
      className={({ isActive }) =>
        cn(
          baseClass,
          collapsed ? "justify-center w-10" : "px-3 gap-3",
          isActive
            ? "bg-bg-tertiary text-text-primary border border-[rgba(255,240,220,0.08)] [&_svg]:text-accent"
            : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/60 border border-transparent [&_svg]:text-text-tertiary",
        )
      }
    >
      <Icon className={cn("shrink-0", collapsed ? "w-[18px] h-[18px]" : "w-[18px] h-[18px]")} />
      {!collapsed && (
        <>
          <span className="flex-1 text-[13px] font-medium">{children}</span>
          {badge && (
            <span
              className={cn(
                "min-w-[20px] h-5 px-1.5 inline-flex items-center justify-center rounded-full",
                "text-[10px] font-semibold tabular-nums",
                badge === "新"
                  ? "bg-accent/15 text-accent border border-accent/30"
                  : "bg-bg-elevated text-text-secondary border border-[rgba(255,240,220,0.06)]",
              )}
            >
              {badge}
            </span>
          )}
        </>
      )}
      {collapsed && badge && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-0.5 inline-flex items-center justify-center rounded-full text-[9px] font-bold tabular-nums bg-accent text-[#140c0c]">
          {badge}
        </span>
      )}
    </NavLink>
  );
}
