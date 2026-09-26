import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ChevronRight, History, Layers, Receipt, Settings as SettingsIcon, Sparkles } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { RightSidebar } from "./RightSidebar";
import { cn } from "@/lib/utils";

const MOBILE_TABS = [
  { to: "/", label: "分析", icon: Layers, testId: "mob-analysis", end: true },
  { to: "/recommendations", label: "信号", icon: Sparkles, testId: "mob-rec" },
  { to: "/trades", label: "交易", icon: Receipt, testId: "mob-trades" },
  { to: "/backtest", label: "回测", icon: History, testId: "mob-backtest" },
  { to: "/settings", label: "设置", icon: SettingsIcon, testId: "mob-settings" },
];

function getSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem("sidebar-collapsed") === "1";
  } catch {
    return false;
  }
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(getSidebarCollapsed);
  const location = useLocation();

  const toggleSidebar = () => {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    try {
      localStorage.setItem("sidebar-collapsed", next ? "1" : "0");
    } catch {}
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-bg-primary text-text-primary bg-warm-spotlight">
      {/* Desktop Sidebar */}
      <div className={cn(
        "hidden lg:block h-full shrink-0 transition-[width] duration-300 ease-in-out overflow-visible",
        sidebarCollapsed ? "w-16" : "w-[248px]",
      )}>
        <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={toggleSidebar} />
      </div>

      {/* Expand button — fixed position when sidebar is collapsed */}
      {sidebarCollapsed && (
        <button
          onClick={toggleSidebar}
          className="hidden lg:flex fixed top-[4.5rem] left-16 z-20 items-center justify-center w-8 h-8 rounded-full bg-bg-secondary border border-[rgba(255,240,220,0.1)] text-text-tertiary hover:text-text-primary hover:border-[rgba(255,240,220,0.2)] transition-colors shadow-lg"
          aria-label="展开侧边栏"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      )}

      {/* Mobile overlay */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden transition-opacity"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Mobile drawer */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-[280px] transform transition-transform duration-300 ease-out lg:hidden",
          isMobileMenuOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <Sidebar onClose={() => setIsMobileMenuOpen(false)} />
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <Topbar onMenuClick={() => setIsMobileMenuOpen(true)} />
        <main className="flex-1 overflow-y-auto pb-20 lg:pb-0">
          <div key={location.pathname} className="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-8 animate-slide-up">
            {children}
          </div>
        </main>
      </div>

      {/* Right Sidebar — global tools (futures calculator, etc.) */}
      <RightSidebar />

      {/* Mobile bottom tab bar */}
      <nav
        className={cn(
          "fixed bottom-0 left-0 right-0 z-30 lg:hidden",
          "border-t border-[rgba(255,240,220,0.06)] bg-bg-primary/95 backdrop-blur-md",
          "px-1 pt-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))]",
        )}
        aria-label="Primary"
      >
        <div className="flex items-stretch justify-around">
          {MOBILE_TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              data-testid={tab.testId}
              className={({ isActive }) =>
                cn(
                  "flex-1 flex flex-col items-center justify-center gap-0.5 min-w-0 py-1 px-1 rounded-xl",
                  "transition-all active:scale-95",
                  isActive ? "text-accent" : "text-text-tertiary",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <tab.icon
                    className={cn(
                      "w-5 h-5 transition-transform",
                      isActive && "scale-110",
                    )}
                    strokeWidth={isActive ? 2.5 : 2}
                  />
                  <span className={cn("text-[10px] font-medium tracking-tight", isActive && "font-semibold")}>
                    {tab.label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
