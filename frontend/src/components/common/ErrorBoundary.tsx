"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertOctagon, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary] Uncaught react error:", error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 bg-slate-900/90 border border-rose-900/50 rounded-xl text-center shadow-xl font-mono space-y-3 my-4">
          <div className="w-10 h-10 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center mx-auto">
            <AlertOctagon className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-bold text-slate-100">
            {this.props.fallbackTitle || "Widget Execution Exception"}
          </h3>
          <p className="text-xs text-rose-300 bg-rose-950/60 p-2.5 rounded border border-rose-900/80 max-w-md mx-auto overflow-x-auto">
            {this.state.error?.message || "An unexpected rendering error occurred."}
          </p>
          <button
            onClick={this.handleRetry}
            className="px-3.5 py-1.5 text-xs bg-rose-600 hover:bg-rose-500 text-white font-medium rounded-lg inline-flex items-center gap-1.5 shadow"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry Component
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
