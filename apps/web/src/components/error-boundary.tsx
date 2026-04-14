"use client";

import React from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  retryCount: number;
}

const MAX_RETRIES = 3;

/**
 * Global error boundary that catches unhandled React errors.
 * Shows a retry UI instead of a blank screen. Limits retries to
 * prevent infinite loops from deterministic errors.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, retryCount: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex min-h-[400px] flex-col items-center justify-center gap-4 p-8 text-center">
          <div className="rounded-full bg-red-50 p-3">
            <AlertTriangle className="h-8 w-8 text-red-500" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              Something went wrong
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              An unexpected error occurred. Please try again.
            </p>
            {this.state.error && (
              <p className="mt-2 max-w-md text-xs text-muted-foreground">
                {this.state.error.message}
              </p>
            )}
          </div>
          {this.state.retryCount < MAX_RETRIES ? (
            <button
              onClick={() =>
                this.setState((prev) => ({
                  hasError: false,
                  error: null,
                  retryCount: prev.retryCount + 1,
                }))
              }
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
            >
              <RotateCcw className="h-4 w-4" />
              Try Again ({MAX_RETRIES - this.state.retryCount} left)
            </button>
          ) : (
            <a
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-lg bg-muted-foreground px-4 py-2 text-sm font-medium text-white hover:bg-muted-foreground/90"
            >
              Go to Dashboard
            </a>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
