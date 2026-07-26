// WS-1.10 view — the end-of-day review: the distilled entry + the one "Keep" choice. Pure render;
// the trigger/poll/keep flow lives in useEndOfDay (CLAUDE.md MVC).
import type { DiaryEntry } from '../types';
import type { EndOfDayStatus } from '../hooks/useEndOfDay';

export function EndOfDayReview({
  status,
  entry,
  error,
  keeping,
  onKeep,
}: {
  status: EndOfDayStatus;
  entry: DiaryEntry | null;
  error: string | null;
  keeping: boolean;
  onKeep: () => void;
}) {
  if (status === 'idle') return null;

  return (
    <div data-testid="assistant-review" className="rounded-lg border border-border bg-card p-4">
      <h3 className="mb-1 text-sm font-semibold">Here&apos;s your day</h3>

      {status === 'distilling' && (
        <p data-testid="assistant-distilling" className="text-sm text-muted-foreground">
          Turning today&apos;s conversation into a diary entry…
        </p>
      )}

      {status === 'error' && (
        <p data-testid="assistant-review-error" className="text-sm text-red-600">
          {error ?? 'Something went wrong.'}
        </p>
      )}

      {status === 'ready' && entry && (
        <div data-testid="assistant-entry">
          <p className="mb-2 text-xs text-muted-foreground">
            <span data-testid="assistant-entry-date">{entry.entry_date}</span>
            {entry.word_count ? ` · ${entry.word_count} words` : ''}
            {entry.kept ? ' · kept' : ''}
          </p>
          <div
            data-testid="assistant-entry-body"
            className="mb-3 max-h-64 overflow-y-auto whitespace-pre-wrap rounded border border-border bg-background p-3 text-sm"
          >
            {entry.body}
          </div>
          <button
            type="button"
            data-testid="assistant-keep-entry"
            onClick={onKeep}
            disabled={keeping || entry.kept}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {entry.kept ? 'Kept ✓' : keeping ? 'Keeping…' : "Keep today's entry"}
          </button>
        </div>
      )}
    </div>
  );
}
