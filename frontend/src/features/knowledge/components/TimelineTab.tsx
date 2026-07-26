import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTimeline } from '../hooks/useTimeline';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { useProjects } from '../hooks/useProjects';
import {
  TIMELINE_SORT_DIRECTIONS,
  TIMELINE_SORT_KEYS,
  type Entity,
  type TimelineSortBy,
  type TimelineSortDir,
} from '../api';
import { TimelineEventRow } from './TimelineEventRow';
import { TimelineFilters } from './TimelineFilters';

// K19e.1 — Timeline tab container. Owns:
//   - projectFilter state
//   - pagination offset (PAGE_SIZE = 50 matches K19d β)
//   - selectedEventId for inline row expansion (single-expand MVP)
//
// BE range params (after_order / before_order) are supported by the
// hook but intentionally not surfaced as UI controls in cycle β. They
// land as a range input in γ or when entity-scope drill-down ships.

// #12 Part 3 — page-size options, matching the glossary entity browser for
// cross-browser consistency. 50 is the back-compat default.
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
const DEFAULT_PAGE_SIZE = 50;

interface TimelineTabProps {
  // C6 (G6) — route-scoped project when hosted inside the project-detail
  // shell. Seeds the filter AND hides the per-tab project `<select>`.
  // Absent ⇒ legacy cross-project surface (dropdown rendered) unchanged.
  scopedProjectId?: string;
}

export function TimelineTab({ scopedProjectId }: TimelineTabProps = {}) {
  const { t, i18n } = useTranslation('knowledge');
  const [projectFilter, setProjectFilter] = useState<string>(
    scopedProjectId ?? '',
  );
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  // C10 (D-K19e-α-01 + D-K19e-α-03) — secondary filters. Entity is
  // stored as the whole Entity object so the chip can show its name
  // without a second lookup; only entity.id is threaded to the BE.
  const [entityFilter, setEntityFilter] = useState<Entity | null>(null);
  const [afterChronological, setAfterChronological] = useState<number | null>(
    null,
  );
  const [beforeChronological, setBeforeChronological] = useState<number | null>(
    null,
  );
  // C14 (C14-narrative-order-sort) — sort axis. Default 'narrative' =
  // reading order (back-compat with the BE's unset default).
  const [sortBy, setSortBy] = useState<TimelineSortBy>('narrative');
  // D-K19e-α-03 — sort direction. Default 'asc' = earliest-first (back-compat).
  const [sortDir, setSortDir] = useState<TimelineSortDir>('asc');
  // D-K19e-α-02 — in-story ISO date-range filter (null = unbounded).
  const [eventDateFrom, setEventDateFrom] = useState<string | null>(null);
  const [eventDateTo, setEventDateTo] = useState<string | null>(null);
  // #12 — free-text search over event title/summary. Debounced so we don't
  // refetch on every keystroke; typing resets the page offset (handled in the
  // input's onChange, not a useEffect, per the FE no-effect-for-events rule).
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebouncedValue(searchInput.trim(), 300);

  const scoped = !!scopedProjectId;
  const effectiveProjectId = scopedProjectId ?? projectFilter;

  const projectsQuery = useProjects(false);

  // C7 /review-impl [L4]: stable callback ref so useTimeline's effect
  // deps don't churn on every TimelineTab render. setOffset's identity
  // is React-guaranteed stable, so [] deps are safe.
  const handleStaleOffset = useCallback(() => setOffset(0), []);

  const { events, total, isLoading, error, isFetching } = useTimeline(
    {
      project_id: effectiveProjectId || undefined,
      entity_id: entityFilter?.id,
      after_chronological: afterChronological ?? undefined,
      before_chronological: beforeChronological ?? undefined,
      event_date_from: eventDateFrom ?? undefined,
      event_date_to: eventDateTo ?? undefined,
      q: debouncedSearch || undefined,
      // KG-TL — forward the active UI language as the reader language so the
      // timeline localizes (chapter heading + participants + summary/time_cue/
      // title). The BE folds it to the primary subtag (zh-TW → zh) and resolves
      // the stored reader-language pref for the scoped project's book; an
      // unscoped browse falls back to this explicit value for chapter titles.
      language: i18n.language || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      limit: pageSize,
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

  const maxOffset = Math.max(0, Math.floor((total - 1) / pageSize) * pageSize);
  const canPrev = offset > 0;
  const canNext = offset + pageSize < total;

  const handleFilterChange = (update: () => void) => {
    update();
    setOffset(0);
  };

  return (
    <div data-testid="timeline-tab">
      {!scoped && (
        <div className="mb-4 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">
              {t('timeline.filters.project')}
            </span>
            <select
              value={projectFilter}
              onChange={(e) =>
                handleFilterChange(() => {
                  setProjectFilter(e.target.value);
                  // C10 — reset secondary filters when project changes.
                  // An entity from project A wouldn't return anything
                  // under project B; chrono bounds tuned to one project
                  // are rarely meaningful in another. Mirrors the C8
                  // drawer-search pattern.
                  setEntityFilter(null);
                  setAfterChronological(null);
                  setBeforeChronological(null);
                  setEventDateFrom(null);
                  setEventDateTo(null);
                })
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
      )}

      {/* #12 — free-text search over event title/summary. Debounced; typing
          resets the page offset so results start from page 1. */}
      <div className="mb-3 relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          value={searchInput}
          onChange={(e) => {
            setSearchInput(e.target.value);
            setOffset(0);
          }}
          placeholder={t('timeline.search.placeholder')}
          aria-label={t('timeline.search.label')}
          className="w-full rounded-md border bg-input py-1.5 pl-8 pr-8 text-xs outline-none focus:border-ring"
          data-testid="timeline-search"
        />
        {searchInput && (
          <button
            type="button"
            onClick={() => {
              setSearchInput('');
              setOffset(0);
            }}
            aria-label={t('timeline.search.clear')}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
            data-testid="timeline-search-clear"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* C14 — sort axis toggle (narrative ↔ chronological). A segmented
          control, NOT a project select — the route owns the project scope
          (G6). Default 'narrative' matches the BE's back-compat default. */}
      <div className="mb-3 flex items-center gap-2 text-[11px]">
        <span className="text-muted-foreground">{t('timeline.sort.label')}</span>
        <div
          className="inline-flex overflow-hidden rounded-md border"
          role="group"
          aria-label={t('timeline.sort.label')}
          data-testid="timeline-sort"
        >
          {TIMELINE_SORT_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={sortBy === key}
              onClick={() => handleFilterChange(() => setSortBy(key))}
              className={cn(
                'px-2.5 py-1 transition-colors',
                sortBy === key
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-secondary',
              )}
              data-testid={`timeline-sort-${key}`}
            >
              {t(`timeline.sort.${key}`)}
            </button>
          ))}
        </div>
        {/* D-K19e-α-03 — direction toggle (asc ↔ desc), applies to the chosen
            axis. Default 'asc' matches the BE back-compat default. */}
        <div
          className="inline-flex overflow-hidden rounded-md border"
          role="group"
          aria-label={t('timeline.sort.direction')}
          data-testid="timeline-sort-dir"
        >
          {TIMELINE_SORT_DIRECTIONS.map((dir) => (
            <button
              key={dir}
              type="button"
              aria-pressed={sortDir === dir}
              onClick={() => handleFilterChange(() => setSortDir(dir))}
              className={cn(
                'px-2.5 py-1 transition-colors',
                sortDir === dir
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-secondary',
              )}
              data-testid={`timeline-sort-dir-${dir}`}
            >
              {t(`timeline.sort.${dir}`)}
            </button>
          ))}
        </div>
      </div>

      {/* C10 — secondary filters (entity + chronological range). Row
          separate from the project select so the entity dropdown has
          enough horizontal room. */}
      <div className="mb-4">
        <TimelineFilters
          projectId={effectiveProjectId || undefined}
          entity={entityFilter}
          onEntityChange={(ent) =>
            handleFilterChange(() => setEntityFilter(ent))
          }
          afterChronological={afterChronological}
          beforeChronological={beforeChronological}
          onChronologicalRangeChange={(after, before) =>
            handleFilterChange(() => {
              setAfterChronological(after);
              setBeforeChronological(before);
            })
          }
          eventDateFrom={eventDateFrom}
          eventDateTo={eventDateTo}
          onDateRangeChange={(from, to) =>
            handleFilterChange(() => {
              setEventDateFrom(from);
              setEventDateTo(to);
            })
          }
        />
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
              <label className="flex items-center gap-1 text-muted-foreground">
                {t('timeline.pagination.pageSize')}
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setOffset(0);
                  }}
                  className="rounded-md border bg-input px-1.5 py-1 outline-none focus:border-ring"
                  data-testid="timeline-page-size"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={!canPrev}
                onClick={() => setOffset(Math.max(0, offset - pageSize))}
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
                  setOffset(Math.min(maxOffset, offset + pageSize))
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
