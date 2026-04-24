import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { Search, RefreshCw } from 'lucide-react';
import { useAuth } from '@/auth';
import type { DrawerSearchHit, DrawerSourceType } from '../api';
import { parseDrawersError } from '../api';
import {
  DRAWER_SEARCH_MIN_QUERY_LENGTH,
  useDrawerSearch,
} from '../hooks/useDrawerSearch';
import { useProjects } from '../hooks/useProjects';
import { DrawerResultCard } from './DrawerResultCard';
import { DrawerDetailPanel } from './DrawerDetailPanel';
import { DrawerSearchFilters } from './DrawerSearchFilters';

// K19e.4 — Raw drawers tab container. Owns:
//   - projectFilter (required — BE rejects searches without project_id)
//   - searchInput + 300ms debounce (matches K19d β entities convention)
//   - selectedHit for the slide-over detail panel
//
// No pagination — drawer search is top-N-by-cosine-similarity, not a
// stable ordered list. Default limit=40 matches the BE default.
//
// Error branching:
//   - retryable=true  → "Retry" button that invalidates the cached
//     query, re-runs the embed + vector search (typical for provider
//     timeouts / 5xx).
//   - retryable=false → "Fix your embedding model" hint with a link
//     back to the project settings.

const SEARCH_DEBOUNCE_MS = 300;
const LIMIT = 40;

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(h);
  }, [value, delayMs]);
  return debounced;
}

export function RawDrawersTab() {
  const { t } = useTranslation('knowledge');
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [projectFilter, setProjectFilter] = useState<string>('');
  const [searchInput, setSearchInput] = useState<string>('');
  const [sourceType, setSourceType] = useState<DrawerSourceType | null>(null);
  const [selectedHit, setSelectedHit] = useState<DrawerSearchHit | null>(null);

  const debouncedQuery = useDebounced(searchInput, SEARCH_DEBOUNCE_MS);
  const projectsQuery = useProjects(false);

  const {
    hits,
    embeddingModel,
    sourceTypeCounts,
    disabled,
    isLoading,
    isFetching,
    error,
  } = useDrawerSearch({
    project_id: projectFilter,
    query: debouncedQuery,
    limit: LIMIT,
    source_type: sourceType ?? undefined,
  });

  const parsedError = error ? parseDrawersError(error) : null;

  const handleRetry = () => {
    // Invalidate by prefix so cached entries across different queries
    // refresh once the provider config is fixed. The userId prefix
    // still scopes it to the caller.
    const userId = user?.user_id ?? 'anon';
    queryClient.invalidateQueries({
      queryKey: ['knowledge-drawers', userId],
    });
  };

  const showNoProject = !projectFilter;
  const showShortQuery =
    !!projectFilter &&
    debouncedQuery.length > 0 &&
    debouncedQuery.length < DRAWER_SEARCH_MIN_QUERY_LENGTH;
  const showEmptyQuery =
    !!projectFilter && debouncedQuery.length === 0;
  const showNotIndexed =
    !disabled && !error && !isLoading && embeddingModel === null;
  const showEmpty =
    !disabled &&
    !error &&
    !isLoading &&
    embeddingModel !== null &&
    hits.length === 0;

  return (
    <div data-testid="raw-drawers-tab">
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[11px]">
          <span className="text-muted-foreground">
            {t('drawers.filters.project')}
          </span>
          <select
            value={projectFilter}
            onChange={(e) => {
              setProjectFilter(e.target.value);
              // C8 /review-impl [MED#3]: reset source_type filter when
              // project changes. Holding e.g. "Chapter" across projects
              // hides hits from a project with only chat passages.
              setSourceType(null);
            }}
            className="rounded-md border bg-input px-2 py-1.5 text-xs outline-none focus:border-ring"
            data-testid="drawers-filter-project"
          >
            <option value="">
              {t('drawers.filters.selectProject')}
            </option>
            {projectsQuery.items.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-1 flex-col gap-1 text-[11px]">
          <span className="text-muted-foreground">
            {t('drawers.searchInput.label')}
          </span>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t('drawers.searchInput.placeholder')}
              disabled={!projectFilter}
              className="w-full rounded-md border bg-input py-1.5 pl-7 pr-2 text-xs outline-none focus:border-ring disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="drawers-search-input"
            />
          </div>
        </label>
      </div>

      {/* C8 — source_type filter pill row. Rendered even when project
          isn't picked yet (counts stay zero-padded) so the layout
          doesn't jump when the user selects a project. */}
      <div className="mb-4">
        <DrawerSearchFilters
          value={sourceType}
          counts={sourceTypeCounts}
          onChange={setSourceType}
          disabled={!projectFilter}
        />
      </div>

      {showNoProject && (
        <p
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="drawers-no-project"
        >
          {t('drawers.noProject')}
        </p>
      )}

      {showEmptyQuery && (
        <p
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="drawers-no-query"
        >
          {t('drawers.noQuery')}
        </p>
      )}

      {showShortQuery && (
        <p
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="drawers-short-query"
        >
          {t('drawers.minQueryHint', {
            min: DRAWER_SEARCH_MIN_QUERY_LENGTH,
          })}
        </p>
      )}

      {isLoading && (
        <div
          className="text-[12px] text-muted-foreground"
          data-testid="drawers-loading"
        >
          {t('drawers.loading')}
        </div>
      )}

      {parsedError && !isLoading && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="drawers-error"
        >
          <p className="mb-2">
            {t('drawers.loadFailed', {
              // Belt-and-braces fallback: if both the server-supplied
              // detailMessage AND the generic Error.message are empty
              // strings (unlikely but not impossible for oddly-shaped
              // error payloads), fall through to a translated
              // "unknown error" so the banner never reads
              // "Search failed:" with trailing whitespace.
              error:
                parsedError.detailMessage ||
                parsedError.message ||
                t('drawers.unknownError'),
            })}
          </p>
          {parsedError.retryable ? (
            <button
              type="button"
              onClick={handleRetry}
              disabled={isFetching}
              className="inline-flex items-center gap-1 rounded-md border border-destructive/40 px-2 py-1 text-[11px] transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="drawers-retry"
            >
              <RefreshCw className="h-3 w-3" />
              {t('drawers.retry')}
            </button>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              {t('drawers.fixConfig')}
            </p>
          )}
        </div>
      )}

      {showNotIndexed && (
        <div
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px]"
          data-testid="drawers-not-indexed"
        >
          <p className="mb-1 font-medium">{t('drawers.notIndexed')}</p>
          <p className="text-muted-foreground">
            {t('drawers.notIndexedHint')}
          </p>
        </div>
      )}

      {showEmpty && (
        <p
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="drawers-empty"
        >
          {t('drawers.empty')}
        </p>
      )}

      {!disabled && !error && !isLoading && hits.length > 0 && (
        <>
          <ul
            className="divide-y overflow-hidden rounded-md border"
            data-testid="drawers-list"
          >
            {hits.map((hit) => (
              <DrawerResultCard
                key={hit.id}
                hit={hit}
                query={debouncedQuery}
                onOpen={() => setSelectedHit(hit)}
              />
            ))}
          </ul>
          {isFetching && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              {t('drawers.refreshing')}
            </p>
          )}
        </>
      )}

      <DrawerDetailPanel
        open={!!selectedHit}
        onOpenChange={(o) => {
          if (!o) setSelectedHit(null);
        }}
        hit={selectedHit}
      />
    </div>
  );
}
