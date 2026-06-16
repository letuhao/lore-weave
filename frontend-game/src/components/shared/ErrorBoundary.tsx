import { Component, type ReactNode } from 'react';

// Reusable React error boundary. Render-phase errors (e.g. a failed `useGLTF`
// glb load or a `React.lazy` chunk fetch) otherwise propagate to the root and
// unmount the whole app (blank screen); this contains them to a fallback UI.
//
// `resetKey`: when it changes, a tripped boundary clears and retries — so e.g.
// picking a different world after one failed to load mounts fresh.

interface Props {
  fallback: ReactNode;
  children: ReactNode;
  resetKey?: unknown;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown): void {
    // Surface for diagnostics; the fallback is what the user sees.
    console.error('ErrorBoundary caught an error:', error);
  }

  componentDidUpdate(prev: Props): void {
    if (this.state.hasError && prev.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  render(): ReactNode {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
