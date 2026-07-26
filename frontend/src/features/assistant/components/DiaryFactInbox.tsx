// WS-2.5 view — the diary FACT INBOX. Pure render; the list + confirm/reject flow lives in
// useDiaryFactInbox (CLAUDE.md MVC). The distiller diverts each day's facts here (human-gated); the
// user promotes the ones worth remembering (→ recallable KG facts) and rejects the rest (→ tombstoned,
// not re-proposed). Shows the structured subject→predicate→object when present, else the raw fact text.
import type { DiaryPendingFact } from '../types';

function factLine(f: DiaryPendingFact): string {
  if (f.subject && f.object) {
    return `${f.subject} · ${f.predicate ?? '—'} · ${f.object}`;
  }
  return f.fact_text;
}

export function DiaryFactInbox({
  facts,
  isLoading,
  error,
  pendingId,
  onConfirm,
  onReject,
}: {
  facts: DiaryPendingFact[];
  isLoading: boolean;
  error: Error | null;
  pendingId: string | null;
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}) {
  // Nothing to review → render nothing (an empty inbox is not an alarming state).
  if (!isLoading && !error && facts.length === 0) return null;

  return (
    <div data-testid="diary-fact-inbox" className="rounded-lg border border-border bg-card p-4">
      <h3 className="mb-1 text-sm font-semibold">
        Facts to remember{facts.length ? ` (${facts.length})` : ''}
      </h3>
      <p className="mb-3 text-xs text-muted-foreground">
        From today&apos;s conversations. Keep the ones worth remembering; dismiss the rest.
      </p>

      {isLoading && (
        <p data-testid="diary-fact-inbox-loading" className="text-sm text-muted-foreground">
          Loading…
        </p>
      )}
      {error && (
        <p data-testid="diary-fact-inbox-error" className="text-sm text-red-600">
          Couldn&apos;t load facts.
        </p>
      )}

      <ul className="space-y-2">
        {facts.map((f) => {
          const busy = pendingId === f.pending_fact_id;
          return (
            <li
              key={f.pending_fact_id}
              data-testid="diary-fact-row"
              className="flex items-center justify-between gap-3 rounded border border-border bg-background p-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm" data-testid="diary-fact-text">
                  {factLine(f)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {f.fact_type}
                  {f.event_date ? ` · ${f.event_date}` : ''}
                  {f.provenance === 'quoted_third_party' ? ' · quoted' : ''}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  data-testid="diary-fact-confirm"
                  onClick={() => onConfirm(f.pending_fact_id)}
                  disabled={busy}
                  className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
                >
                  {busy ? '…' : 'Keep'}
                </button>
                <button
                  type="button"
                  data-testid="diary-fact-reject"
                  onClick={() => onReject(f.pending_fact_id)}
                  disabled={busy}
                  className="rounded-md border border-border px-3 py-1 text-xs font-medium disabled:opacity-50"
                >
                  Dismiss
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
