import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { CheckCircle2, AlertTriangle, Info, X, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info" | "warning";

interface Toast {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
  duration: number;
}

interface ToastContextValue {
  show: (toast: PartialBy<Omit<Toast, "id">, "duration" | "tone">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
  info: (title: string, description?: string) => void;
  warning: (title: string, description?: string) => void;
  dismiss: (id: string) => void;
}

type PartialBy<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

const TONE_STYLES: Record<ToastTone, { icon: ReactNode; border: string; iconColor: string }> = {
  success: {
    icon: <CheckCircle2 className="w-4 h-4" />,
    border: "border-bull/30",
    iconColor: "text-bull",
  },
  error: {
    icon: <AlertCircle className="w-4 h-4" />,
    border: "border-bear/30",
    iconColor: "text-bear",
  },
  warning: {
    icon: <AlertTriangle className="w-4 h-4" />,
    border: "border-warning/30",
    iconColor: "text-warning",
  },
  info: {
    icon: <Info className="w-4 h-4" />,
    border: "border-info/30",
    iconColor: "text-info",
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (toast: PartialBy<Omit<Toast, "id">, "duration" | "tone">) => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const next: Toast = { id, duration: 3500, tone: "info", ...toast };
      setToasts((prev) => [...prev, next]);
      if (next.duration > 0) {
        setTimeout(() => dismiss(id), next.duration);
      }
    },
    [dismiss],
  );

  const helpers: Pick<ToastContextValue, "success" | "error" | "info" | "warning"> = {
    success: (title, description) => show({ title, description, tone: "success" }),
    error: (title, description) => show({ title, description, tone: "error", duration: 5000 }),
    info: (title, description) => show({ title, description, tone: "info" }),
    warning: (title, description) => show({ title, description, tone: "warning" }),
  };

  return (
    <ToastContext.Provider value={{ show, ...helpers, dismiss }}>
      {children}
      <ToastViewport toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

function ToastViewport({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: string) => void }) {
  return (
    <div
      className="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full pointer-events-none"
      role="region"
      aria-label="Notifications"
    >
      {toasts.map((toast) => {
        const styles = TONE_STYLES[toast.tone];
        return (
          <div
            key={toast.id}
            role="status"
            className={cn(
              "pointer-events-auto rounded-2xl bg-bg-secondary border shadow-2xl",
              "px-4 py-3 flex items-start gap-3",
              "animate-slide-up",
              styles.border,
            )}
          >
            <span className={cn("mt-0.5 shrink-0", styles.iconColor)}>{styles.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-text-primary">{toast.title}</div>
              {toast.description && (
                <div className="text-xs text-text-secondary mt-0.5">{toast.description}</div>
              )}
            </div>
            <button
              onClick={() => dismiss(toast.id)}
              className="p-0.5 -mt-0.5 -mr-0.5 rounded-full text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors shrink-0"
              aria-label="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
