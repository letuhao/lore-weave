// W6 — render error boundary for the two always-mounted motif dock panels
// (motifs · conformance). CompositionPanel mounts EVERY sub-panel simultaneously
// (CSS-hidden, per the CLAUDE.md "never unmount stateful components" rule), and the
// studio has no error isolation — so a single panel that throws during render
// white-screens the ENTIRE editor. This boundary contains a motif-panel crash to a
// small in-panel fallback (e.g. the conformance FE↔BE shape drift,
// D-MOTIF-CONFORMANCE-CONTRACT) instead of taking down the whole studio.
//
// React error boundaries must be class components. Render-only; no app logic.
import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = { label: string; children: ReactNode };
type State = { error: Error | null };

export class MotifPanelBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface for diagnostics; never rethrow (that would re-crash the studio).
    // eslint-disable-next-line no-console
    console.error(`[motif panel: ${this.props.label}] render error`, error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div
          data-testid={`motif-panel-error-${this.props.label}`}
          className="m-2 rounded border border-amber-400 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-500/40 dark:bg-amber-950/30 dark:text-amber-200"
          role="alert"
        >
          <p className="font-medium">This panel hit an error and was contained.</p>
          <p className="mt-1 opacity-80">The rest of the studio is unaffected.</p>
          <button
            type="button"
            data-testid={`motif-panel-error-retry-${this.props.label}`}
            className="mt-2 rounded border border-amber-400 px-2 py-0.5 text-[11px] hover:bg-amber-100 dark:hover:bg-amber-900/40"
            onClick={this.reset}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
