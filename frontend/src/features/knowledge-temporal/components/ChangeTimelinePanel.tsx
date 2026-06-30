import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useTimeline } from '../hooks/useTemporalReads';
import type { TimelineEntry } from '../types';
import type { TemporalSurfaceProps } from './CanonicalCard';

// knowledge-temporal X6c — the entity's bi-temporal change feed (KAL timeline read).
// Renders newest-first fact-change rows with their valid interval, a derived kind badge,
// and the citation (quote + chapter) when the read carries one. Pagination is cursor-based:
// the hook returns one page + a next_cursor, so we accumulate pages by rendering one
// <TimelinePage> child per fetched cursor (effect-free — each child owns its own useTimeline
// call, the tail child renders "load more" from its own nextCursor). Each page degrades
// independently: a sparse/failed read shows an inline message, never crashes the panel.

const PAGE_LIMIT = 25;

type BadgeKind = 'invalidated' | 'closed' | 'open';

/** Derive the change kind from the fact's bi-temporal state (precedence: invalidated → closed → open). */
function deriveKind(entry: TimelineEntry): BadgeKind {
  if (entry.invalidated_at) return 'invalidated';
  if (entry.valid_to_ordinal != null) return 'closed';
  return 'open';
}

function KindBadge({ kind }: { kind: BadgeKind }) {
  const { t } = useTranslation('knowledge');
  const label =
    kind === 'invalidated'
      ? t('temporal.timeline.kind.invalidated', 'invalidated')
      : kind === 'closed'
        ? t('temporal.timeline.kind.superseded', 'superseded')
        : t('temporal.timeline.kind.open', 'open');
  return (
    <span
      data-testid={`timeline-kind-${kind}`}
      className={cn(
        'inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[10px] font-medium',
        kind === 'invalidated' && 'bg-destructive/10 text-destructive',
        kind === 'closed' && 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
        kind === 'open' && 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
      )}
    >
      {label}
    </span>
  );
}

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const { t } = useTranslation('knowledge');
  const kind = deriveKind(entry);
  const open = entry.valid_to_ordinal == null;
  // Interval: [from → to|open). The trailing brace is "]" when closed, ")" when open (+∞).
  const interval = open
    ? t('temporal.timeline.interval.open', '[{{from}} → open)', { from: entry.valid_from_ordinal })
    : t('temporal.timeline.interval.closed', '[{{from}} → {{to}}]', {
        from: entry.valid_from_ordinal,
        to: entry.valid_to_ordinal,
      });
  return (
    <li className="px-3 py-2 text-[12px]" data-testid="timeline-row">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <span className="font-medium text-foreground break-words">{entry.attr_or_predicate}</span>
          <span className="text-muted-foreground"> · </span>
          <span className="break-words text-foreground/90">{entry.value}</span>
        </div>
        <KindBadge kind={kind} />
      </div>
      <div className="mt-0.5 font-mono text-[10px] text-muted-foreground" data-testid="timeline-interval">
        {interval}
      </div>
      {entry.quote ? (
        <blockquote
          className="mt-1 border-l-2 border-muted pl-2 text-[11px] italic text-muted-foreground"
          data-testid="timeline-citation"
        >
          “{entry.quote}”
          {entry.source_chapter_id ? (
            <span className="ml-1 not-italic opacity-70">
              {t('temporal.timeline.chapter', 'ch. {{chapter}}', { chapter: entry.source_chapter_id })}
            </span>
          ) : null}
        </blockquote>
      ) : null}
    </li>
  );
}

/**
 * One fetched page of the change feed. Owns its own useTimeline call (keyed by its cursor),
 * renders its rows, and — when it is the tail page — the "load more" button driven by its own
 * next_cursor. This keeps accumulation effect-free: the parent only tracks the cursor list.
 */
function TimelinePage({
  bookId,
  entityId,
  cursor,
  isTail,
  onLoadMore,
}: {
  bookId: string;
  entityId: string;
  cursor?: string;
  isTail: boolean;
  onLoadMore: (next: string) => void;
}) {
  const { t } = useTranslation('knowledge');
  const { items, nextCursor, isLoading, error } = useTimeline(bookId, entityId, {
    cursor,
    limit: PAGE_LIMIT,
  });

  if (isLoading) {
    return (
      <li className="px-3 py-4 text-center text-[12px] text-muted-foreground" data-testid="timeline-loading">
        {t('temporal.timeline.loading', 'Loading changes…')}
      </li>
    );
  }
  if (error) {
    return (
      <li
        role="alert"
        className="px-3 py-3 text-[12px] text-destructive"
        data-testid="timeline-error"
      >
        {t('temporal.timeline.loadFailed', 'Could not load the change timeline: {{error}}', {
          error: error.message,
        })}
      </li>
    );
  }

  return (
    <>
      {items.map((entry) => (
        <TimelineRow key={entry.fact_id} entry={entry} />
      ))}
      {isTail && nextCursor ? (
        <li className="px-3 py-2 text-center" data-testid="timeline-load-more-wrap">
          <button
            type="button"
            onClick={() => onLoadMore(nextCursor)}
            className="inline-flex items-center rounded-md border px-2.5 py-1 text-[11px] transition-colors hover:bg-secondary"
            data-testid="timeline-load-more"
          >
            {t('temporal.timeline.loadMore', 'Load more')}
          </button>
        </li>
      ) : null}
    </>
  );
}

/**
 * View (render-only delegate of the cursor list) for the entity's bi-temporal change feed.
 * Newest-first rows come from the KAL timeline read (the BE orders the page); the FE only
 * paginates via the cursor and derives the kind badge / interval. Empty + loading + error are
 * surfaced inline so the panel never crashes on a sparse read.
 */
export function ChangeTimelinePanel({ bookId, entityId }: TemporalSurfaceProps) {
  const { t } = useTranslation('knowledge');
  // The cursor list: the first page is fetched with an undefined cursor; "load more" appends
  // the tail page's next_cursor. Local accumulation — no effects, no global mutation.
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);

  // First-page loading/empty state. We read the head page here (cheap — react-query dedupes it
  // with the first <TimelinePage>'s identical query key) to render the section-level empty card.
  const head = useTimeline(bookId, entityId, { limit: PAGE_LIMIT });
  const hasOnlyHead = cursors.length === 1;
  const showEmpty = hasOnlyHead && !head.isLoading && !head.error && head.items.length === 0;

  return (
    <section data-testid="change-timeline" className="space-y-2">
      <h3 className="text-[12px] font-semibold text-foreground">
        {t('temporal.timeline.title', 'Change timeline')}
      </h3>

      {showEmpty ? (
        <div
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="timeline-empty"
        >
          {t('temporal.timeline.empty', 'No recorded changes for this entity yet.')}
        </div>
      ) : (
        <ul className="divide-y overflow-hidden rounded-md border" data-testid="timeline-list">
          {cursors.map((cursor, i) => (
            <TimelinePage
              key={cursor ?? '__head__'}
              bookId={bookId}
              entityId={entityId}
              cursor={cursor}
              isTail={i === cursors.length - 1}
              onLoadMore={(next) => setCursors((prev) => [...prev, next])}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
