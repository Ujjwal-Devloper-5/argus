import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false, error: null };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Argus Dashboard Module Crash:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 bg-card rounded-xl border border-destructive/30 text-center">
          <AlertTriangle className="w-12 h-12 text-destructive mb-4 animate-pulse" />
          <h3 className="text-lg font-bold text-foreground">
            {this.props.fallbackTitle || 'Module Rendering Interrupted'}
          </h3>
          <p className="text-sm text-muted-foreground mt-1 max-w-md">
            {this.state.error?.message || 'An unexpected UI error occurred.'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-6 flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 text-sm font-medium transition-colors"
          >
            <RefreshCw className="w-4 h-4" /> Reset Module
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
