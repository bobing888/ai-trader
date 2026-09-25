import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { Button } from "@/components/ui/Button";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** Catches uncaught React errors and shows a recoverable fallback UI. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info.componentStack);
    try {
      localStorage.setItem(
        "__last_error__",
        JSON.stringify({
          message: error.message,
          stack: error.stack,
          componentStack: info.componentStack,
          at: new Date().toISOString(),
        }),
      );
    } catch {
      /* localStorage may be disabled — non-fatal */
    }
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    const { children, fallback } = this.props;
    if (!error) return children;

    if (fallback) return fallback(error, this.reset);

    return (
      <div className="p-6">
        <ErrorState
          title="页面出错了"
          description={error.message || "意外错误，请刷新页面重试。"}
          action={
            <Button variant="primary" onClick={this.reset}>
              重试
            </Button>
          }
        />
      </div>
    );
  }
}
