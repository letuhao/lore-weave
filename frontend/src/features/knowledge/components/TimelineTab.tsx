import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTimeline } from '../hooks/useTimeline';
import { useProjects } from '../hooks/useProjects';
import { TimelineEventRow } from './TimelineEventRow';

// K19e.1 — Timeline tab container. Owns:
//   - projectFilter state
//   - pagination offset (PAGE_SIZE = 50 matches K19d β)
//   - selectedEventId for inline row expansion (single-expand MVP)
//
// BE range params (after_order / before_order) are supported by the
// hook but intentionally not surfaced as UI controls in cycle β. They
// land as a range input in γ or when entity-scope drill-down ships.

const PAGE_SIZE = 50;

export function TimelineTab() {
  const { t } = useTranslation('knowledge');
  const [projectFilter, setProjectFilter] = useState<string>('');
  const [offset, setOffset] = useState(0);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const projectsQuery = useProjects(false);

  // C7 /review-impl [L4]: stable callback ref so useTimeline's effect
  // deps don't churn on every TimelineTab render. setOffset's identity
  // is React-guaranteed stable, so [] deps are safe.
  const handleStaleOffset = useCallback(() => setOffset(0), []);

  const { events, total, isLoading, error, isFetching } = useTimeline(
    {
      project_id: projectFilter || undefined,
      limit: PAGE_SIZE,
      offset,
    },
    {
      // C7 (D-K19e-β-02) — auto self-heal past-end offset. Keeps the
      // "Back to first" button below as a defense-in-depth fallback
      // for edge cases where the guards (isFetching etc.) gate a click
      // faster than the effect fires.
      onStaleOffset: handleStaleOffset,
    },
  );

  const maxOffset = Math.max(0, Math.floor((total - 1) / PAGE_SIZE) * PAGE_SIZE);
  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  const handleFilterChange = (update: () => void) => {
    update();
    setOffset(0);
  };

  return (
    <div data-testid="timeline-tab">
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[11px]">
          <span className="text-muted-foreground">
            {t('timeline.filters.project')}
          </span>
          <select
            value={projectFilter}
            onChange={(e) =>
              handleFilterChange(() => setProjectFilter(e.target.value))
            }
            className="rounded-md border bg-input px-2 py-1.5 text-xs outline-none focus:border-ring"
            data-testid="timeline-filter-project"
          >
            <option value="">{t('timeline.filters.anyProject')}</option>
            {projectsQuery.items.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && (
        <div
          className="text-[12px] text-muted-foreground"
          data-testid="timeline-loading"
        >
          {t('timeline.loading')}
        </div>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="timeline-error"
        >
          {t('timeline.loadFailed', { error: error.message })}
        </div>
      )}

      {!isLoading && !error && events.length === 0 && (
        <div
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="timeline-empty"
        >
          <p>
            {total === 0
              ? t('timeline.empty')
              : t('timeline.emptyForFilters')}
          </p>
          {/* Past-end offset can strand a user on an empty page when a
              delete cascade shrinks total below their current offset
              (review-impl L6). The "go to first page" button is the
              escape hatch — trivial to add, meaningful UX rescue. */}
          {total > 0 && offset > 0 && (
            <button
              type="button"
              onClick={() => setOffset(0)}
              className="mt-3 inline-flex items-center rounded-md border px-2.5 py-1 text-[11px] transition-colors hover:bg-secondary"
              data-testid="timeline-empty-reset"
            >
              {t('timeline.pagination.backToFirst')}
            </button>
          )}
        </div>
      )}

      {!isLoading && !error && events.length > 0 && (
        <>
          <ul
            className="divide-y overflow-hidden rounded-md border"
            data-testid="timeline-list"
          >
            {events.map((ev) => (
              <TimelineEventRow
                key={ev.id}
                event={ev}
                isExpanded={ev.id === selectedEventId}
                onToggle={() =>
                  setSelectedEventId((prev) => (prev === ev.id ? null : ev.id))
                }
              />
            ))}
          </ul>

          <div className="mt-3 flex items-center justify-between text-[11px]">
            <span
              className="text-muted-foreground"
              data-testid="timeline-pagination-range"
            >
              {t('timeline.pagination.range', {
                from: offset + 1,
                to: Math.min(offset + events.length, total),
                total,
              })}
              {isFetching && (
                <span className="ml-2 text-muted-foreground/70">
                  {t('timeline.pagination.refreshing')}
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!canPrev}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="timeline-pagination-prev"
              >
                <ChevronLeft className="h-3 w-3" />
                {t('timeline.pagination.prev')}
              </button>
              <button
                type="button"
                disabled={!canNext}
                onClick={() =>
                  setOffset(Math.min(maxOffset, offset + PAGE_SIZE))
                }
                className="inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="timeline-pagination-next"
              >
                {t('timeline.pagination.next')}
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
