import { Component, type ErrorInfo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { reportClientError } from '@/lib/clientErrorReporter';

type Props = { children: ReactNode };
type State = { error: Error | null };

/** The fallback is split out as a function component for one reason: an error boundary has to be
 *  a class (getDerivedStateFromError has no hook equivalent), and a class cannot call
 *  useTranslation. Leaving the strings inline is what made this screen ship untranslated. */
function ErrorFallback({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useTranslation('common');
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <section className="w-full max-w-lg rounded-lg border border-amber-400/50 bg-card p-6 shadow-sm" role="alert">
        <h1 className="text-lg font-semibold">
          {t('errorBoundary.title', { defaultValue: 'This page could not be displayed' })}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {t('errorBoundary.description', {
            defaultValue: 'An interface error occurred. It has been saved to the diagnostics log; please try the operation again.',
          })}
        </p>
        <p className="mt-3 rounded bg-muted p-2 font-mono text-xs break-words">{message}</p>
        <button type="button" onClick={onRetry} className="mt-4 rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground">
          {t('errorBoundary.retry', { defaultValue: 'Try again' })}
        </button>
      </section>
    </main>
  );
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    reportClientError(error, { source: 'react-error-boundary', componentStack: info.componentStack ?? undefined });
  }

  private retry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return <ErrorFallback message={this.state.error.message} onRetry={this.retry} />;
  }
}
