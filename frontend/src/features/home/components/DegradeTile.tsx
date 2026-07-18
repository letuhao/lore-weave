// M2 view helper — renders a home tile by its degrade status (spec MB2): a down source shows a
// quiet retry (never blanks the page), an empty source shows honest empty copy, an ok source shows
// its content. Pure view.
import type { TileStatus } from '../types';

export function DegradeTile({
  status,
  title,
  action,
  emptyText,
  onRetry,
  loading,
  children,
}: {
  status: TileStatus;
  title: string;
  action?: React.ReactNode;
  emptyText: string;
  onRetry?: () => void;
  /** While true, show a neutral loading line instead of empty/degraded copy (M3 — don't assert
   *  "all caught up" before data arrives). */
  loading?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : status === 'degraded' ? (
        <p className="text-sm text-muted-foreground">
          Couldn&apos;t load right now.{' '}
          {onRetry && (
            <button type="button" onClick={onRetry} className="text-primary underline-offset-2 hover:underline">
              Retry
            </button>
          )}
        </p>
      ) : status === 'empty' ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        children
      )}
    </section>
  );
}
