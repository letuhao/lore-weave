import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEntities } from '../hooks/useEntities';
import type { Entity } from '../api';

// C10 (D-K19e-α-01 + D-K19e-α-03) — secondary filter bar for the
// Timeline tab: entity picker + chronological range. Rendered below
// the primary project select and above the event list.
//
// Entity picker UX: search input + dropdown of up to 8 matches
// (reuses `useEntities` with min-2-chars debounce matching
// EntityMergeDialog). Selected entity shows as a chip with an X
// button to clear. When `projectId` is set, the entity search is
// scoped to that project so the picker doesn't surface entities from
// unrelated projects the user isn't filtering for.
//
// Chronological range: two number inputs (After / Before). A
// client-side "reversed range" hint renders when after ≥ before;
// the BE 422 is still the authority.

export interface TimelineFiltersProps {
  projectId?: string;
  entity: Entity | null;
  onEntityChange: (entity: Entity | null) => void;
  afterChronological: number | null;
  beforeChronological: number | null;
  onChronologicalRangeChange: (
    after: number | null,
    before: number | null,
  ) => void;
  disabled?: boolean;
}

const ENTITY_DROPDOWN_LIMIT = 8;

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(h);
  }, [value, delayMs]);
  return debounced;
}

export function TimelineFilters({
  projectId,
  entity,
  onEntityChange,
  afterChronological,
  beforeChronological,
  onChronologicalRangeChange,
  disabled,
}: TimelineFiltersProps) {
  const { t } = useTranslation('knowledge');
  const [searchInput, setSearchInput] = useState('');
  const [focused, setFocused] = useState(false);
  const debouncedSearch = useDebounced(searchInput, 250);

  // Min-2-chars rule matches BE Query(min_length=2); drop shorter
  // search queries to keep the dropdown quiet while the user types
  // the first letter.
  const effectiveSearch =
    debouncedSearch.trim().length >= 2 ? debouncedSearch.trim() : undefined;
  const { entities, isLoading } = useEntities({
    project_id: projectId || undefined,
    search: effectiveSearch,
    limit: ENTITY_DROPDOWN_LIMIT,
    offset: 0,
  });

  const showDropdown =
    focused && !entity && !!effectiveSearch && entities.length > 0;

  const reversedChrono =
    afterChronological != null &&
    beforeChronological != null &&
    afterChronological >= beforeChronological;

  const parseNum = (raw: string): number | null => {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const n = Number(trimmed);
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : null;
  };

  // C10 /review-impl [MED#1]: debounce chronological input commits.
  // Without this, every keystroke (typing "1500" = 4 strokes) fires
  // a parent onChange → useTimeline queryKey change → new BE call.
  // Pattern: local state for the raw input string + a 400ms delayed
  // commit to the parent when the parsed value differs from props.
  // The parent still owns the canonical filter state (props drive
  // chips, reset-on-project-change, etc.) — the local state is a
  // pure typing buffer.
  const [afterInput, setAfterInput] = useState(
    afterChronological == null ? '' : String(afterChronological),
  );
  const [beforeInput, setBeforeInput] = useState(
    beforeChronological == null ? '' : String(beforeChronological),
  );

  // Sync from parent when props change (parent-driven resets like
  // project change clearing the filter).
  useEffect(() => {
    setAfterInput(afterChronological == null ? '' : String(afterChronological));
  }, [afterChronological]);
  useEffect(() => {
    setBeforeInput(
      beforeChronological == null ? '' : String(beforeChronological),
    );
  }, [beforeChronological]);

  // Debounced commit. The effect re-runs when the local input strings
  // change; it clears the pending timeout and schedules a new one.
  // When props change from parent reset, both inputs match immediately
  // so the no-change guard inside the timeout skips the callback.
  const parsedAfter = parseNum(afterInput);
  const parsedBefore = parseNum(beforeInput);
  useEffect(() => {
    const changed =
      parsedAfter !== afterChronological ||
      parsedBefore !== beforeChronological;
    if (!changed) return;
    const h = setTimeout(() => {
      onChronologicalRangeChange(parsedAfter, parsedBefore);
    }, 400);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parsedAfter, parsedBefore]);

  const afterStr = afterInput;
  const beforeStr = beforeInput;

  return (
    <div
      className="flex flex-wrap items-end gap-3"
      data-testid="timeline-filters"
    >
      {/* Entity picker */}
      <div className="flex flex-col gap-1 text-[11px]">
        <label className="text-muted-foreground" htmlFor="timeline-entity-input">
          {t('timeline.filters.entity')}
        </label>
        {entity ? (
          <div
            className="inline-flex items-center gap-1 rounded-md border bg-primary/5 px-2 py-1 text-[12px]"
            data-testid="timeline-filter-entity-selected"
          >
            <span className="truncate">{entity.name}</span>
            <button
              type="button"
              onClick={() => {
                onEntityChange(null);
                setSearchInput('');
              }}
              disabled={disabled}
              aria-label={t('timeline.filters.clearEntity')}
              className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="timeline-filter-entity-clear"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input
              id="timeline-entity-input"
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onFocus={() => setFocused(true)}
              // Blur happens on mousedown of a dropdown item before click;
              // delay hide slightly so the click registers. The dropdown
              // gating (`showDropdown`) already hides on selection.
              onBlur={() => window.setTimeout(() => setFocused(false), 150)}
              placeholder={t('timeline.filters.entityPlaceholder')}
              disabled={disabled}
              className="w-48 rounded-md border bg-input py-1.5 pl-7 pr-2 text-xs outline-none focus:border-ring disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="timeline-filter-entity-input"
            />
            {showDropdown && (
              <ul
                className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-md border bg-background text-[12px] shadow-md"
                data-testid="timeline-filter-entity-dropdown"
              >
                {entities.slice(0, ENTITY_DROPDOWN_LIMIT).map((ent) => (
                  <li key={ent.id}>
                    <button
                      type="button"
                      onMouseDown={(ev) => {
                        // Prevent input blur before the click lands.
                        ev.preventDefault();
                      }}
                      onClick={() => {
                        onEntityChange(ent);
                        setSearchInput('');
                      }}
                      className="flex w-full items-center justify-between px-2 py-1.5 text-left hover:bg-secondary"
                      data-testid={`timeline-filter-entity-option-${ent.id}`}
                    >
                      <span className="truncate">{ent.name}</span>
                      <span className="ml-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                        {ent.kind}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {focused &&
              !entity &&
              searchInput.trim().length > 0 &&
              searchInput.trim().length < 2 && (
                <p
                  className="mt-1 text-[10px] text-muted-foreground"
                  data-testid="timeline-filter-entity-min-hint"
                >
                  {t('timeline.filters.entitySearchMinHint')}
                </p>
              )}
            {focused &&
              !entity &&
              !!effectiveSearch &&
              !isLoading &&
              entities.length === 0 && (
                <p
                  className="mt-1 text-[10px] text-muted-foreground"
                  data-testid="timeline-filter-entity-empty"
                >
                  {t('timeline.filters.entityNoMatches')}
                </p>
              )}
          </div>
        )}
      </div>

      {/* Chronological range */}
      <fieldset
        className={cn(
          'flex items-end gap-2 text-[11px]',
          disabled && 'opacity-50',
        )}
        data-testid="timeline-filter-chrono"
        disabled={disabled}
      >
        <legend className="sr-only">
          {t('timeline.filters.chronologicalRange')}
        </legend>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">
            {t('timeline.filters.after')}
          </span>
          <input
            type="number"
            min={0}
            inputMode="numeric"
            value={afterStr}
            onChange={(ev) => setAfterInput(ev.target.value)}
            className="w-20 rounded-md border bg-input px-2 py-1.5 text-xs outline-none focus:border-ring disabled:cursor-not-allowed"
            data-testid="timeline-filter-chrono-after"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">
            {t('timeline.filters.before')}
          </span>
          <input
            type="number"
            min={0}
            inputMode="numeric"
            value={beforeStr}
            onChange={(ev) => setBeforeInput(ev.target.value)}
            className="w-20 rounded-md border bg-input px-2 py-1.5 text-xs outline-none focus:border-ring disabled:cursor-not-allowed"
            data-testid="timeline-filter-chrono-before"
          />
        </label>
        {reversedChrono && (
          <p
            role="alert"
            className="text-[10px] text-destructive"
            data-testid="timeline-filter-chrono-reversed"
          >
            {t('timeline.filters.chronoReversed')}
          </p>
        )}
      </fieldset>
    </div>
  );
}
