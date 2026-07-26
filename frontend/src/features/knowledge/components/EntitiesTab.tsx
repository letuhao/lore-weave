import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Sparkles, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { useEntities } from '../hooks/useEntities';
import { useProjects } from '../hooks/useProjects';
import { EntitiesTable } from './EntitiesTable';
import { EntityDetailPanel } from './EntityDetailPanel';
import { EntityStatusLegend } from './EntityStatusLegend';
import { CreateEntityDialog } from './CreateEntityDialog';
import { ENTITY_STATUSES, type EntityStatus } from '../api';

// K19d — Entities tab container. Owns:
//   - filter state (project_id, kind, search — all nullable/free)
//   - pagination state (offset, limit fixed at 50)
//   - selected entity id for the detail panel
//
// Search is debounced to avoid thrashing the BE's CONTAINS scan on
// every keystroke. The FE enforces the 2-char minimum that matches
// the BE Query(min_length=2) — shorter inputs just don't dispatch
// a search param so the BE returns the unfiltered list instead of a
// 422.

const PAGE_SIZE = 50;

const KIND_OPTIONS = [
  'character',
  'location',
  'organization',
  'concept',
  'item',
  'event_ref',
  'preference',
] as const;

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(h);
  }, [value, delayMs]);
  return debounced;
}

interface EntitiesTabProps {
  // C6 (G6) — when rendered inside the project-detail shell the project
  // scope comes from the ROUTE, not a select-box. Providing this both
  // seeds the project filter AND hides the per-tab project `<select>`
  // (the G6 IA backbone). Absent ⇒ the legacy cross-project surface with
  // its dropdown is unchanged.
  scopedProjectId?: string;
}

export function EntitiesTab({ scopedProjectId }: EntitiesTabProps = {}) {
  const { t } = useTranslation('knowledge');
  const [projectFilter, setProjectFilter] = useState<string>(
    scopedProjectId ?? '',
  );
  const [kindFilter, setKindFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<EntityStatus | ''>('');
  const [searchInput, setSearchInput] = useState<string>('');
  const [semanticInput, setSemanticInput] = useState<string>('');
  const [offset, setOffset] = useState(0);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const debouncedSearch = useDebounced(searchInput, 300);
  const debouncedSemantic = useDebounced(semanticInput, 300);

  const scoped = !!scopedProjectId;
  // When scoped by route, the route param is authoritative; the internal
  // projectFilter state is only used by the cross-project (unscoped) view.
  const effectiveProjectId = scopedProjectId ?? projectFilter;

  // C8: semantic VECTOR search requires a project (BE 422s otherwise).
  // The box is only offered when scoped, and it is mutually exclusive
  // with the plain FTS `search` (BE 422s if both set) — semantic wins
  // when both have text.
  const effectiveSemantic =
    scoped && debouncedSemantic.length >= 2 ? debouncedSemantic : undefined;
  const effectiveSearch =
    !effectiveSemantic && debouncedSearch.length >= 2
      ? debouncedSearch
      : undefined;

  const projectsQuery = useProjects(false);

  // C9 — the scoped project's linked book, threaded to the detail panel
  // for the glossary context-pin toggle (book-scoped). Resolved from the
  // already-loaded projects list; null when the project has no book.
  const scopedBookId =
    projectsQuery.items.find((p) => p.project_id === effectiveProjectId)
      ?.book_id ?? null;

  const { entities, total, isLoading, error, isFetching } = useEntities({
    project_id: effectiveProjectId || undefined,
    kind: kindFilter || undefined,
    search: effectiveSearch,
    semantic_query: effectiveSemantic,
    status: statusFilter || undefined,
    sort_by: 'anchor_score',
    limit: PAGE_SIZE,
    offset,
  });

  const maxOffset = Math.max(0, Math.floor((total - 1) / PAGE_SIZE) * PAGE_SIZE);
  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  const handleFilterChange = (update: () => void) => {
    update();
    setOffset(0); // Filter change resets pagination.
  };

  return (
    <div data-testid="entities-tab">
      <div className="mb-4 flex flex-wrap items-end gap-2">
        {!scoped && (
          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">
              {t('entities.filters.project')}
            </span>
            <select
              value={projectFilter}
              onChange={(e) =>
                handleFilterChange(() => setProjectFilter(e.target.value))
              }
              className="rounded-md border bg-input px-2 py-1.5 text-xs outline-none focus:border-ring"
              data-testid="entities-filter-project"
            >
              <option value="">{t('entities.filters.anyProject')}</option>
              {projectsQuery.items.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <label className="flex flex-col gap-1 text-[11px]">
          <span className="text-muted-foreground">
            {t('entities.filters.kind')}
          </span>
          <select
            value={kindFilter}
            onChange={(e) =>
              handleFilterChange(() => setKindFilter(e.target.value))
            }
            className="rounded-md border bg-input px-2 py-1.5 text-xs outline-none focus:border-ring"
            data-testid="entities-filter-kind"
          >
            <option value="">{t('entities.filters.anyKind')}</option>
            {KIND_OPTIONS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-[11px]">
          <span className="text-muted-foreground">
            {t('entities.filters.status')}
          </span>
          <select
            value={statusFilter}
            onChange={(e) =>
              handleFilterChange(() =>
                setStatusFilter(e.target.value as EntityStatus | ''),
              )
            }
            className="rounded-md border bg-input px-2 py-1.5 text-xs outline-none focus:border-ring"
            data-testid="entities-filter-status"
          >
            <option value="">{t('entities.filters.anyStatus')}</option>
            {ENTITY_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`entities.status.${s}`)}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-1 flex-col gap-1 text-[11px]">
          <span className="text-muted-foreground">
            {t('entities.filters.search')}
          </span>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) =>
                handleFilterChange(() => setSearchInput(e.target.value))
              }
              placeholder={t('entities.filters.searchPlaceholder')}
              className="w-full rounded-md border bg-input py-1.5 pl-7 pr-2 text-xs outline-none focus:border-ring"
              data-testid="entities-filter-search"
            />
          </div>
        </label>

        {/* S7-1 — hand-author a new entity. Disabled with no project selected
            (a node must attach to a project tag). */}
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          disabled={!effectiveProjectId}
          title={
            effectiveProjectId
              ? undefined
              : t('entities.create.needsProject')
          }
          data-testid="entities-new-button"
          className="inline-flex items-center gap-1.5 self-end rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-3 w-3" />
          {t('entities.create.newButton')}
        </button>
      </div>

      {effectiveProjectId && (
        <CreateEntityDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          projectId={effectiveProjectId}
        />
      )}

      {/* C8: semantic VECTOR search box — distinct from plain FTS. Only
          when scoped (BE requires a project for vector search). */}
      {scoped && (
        <label
          className="mb-3 flex flex-col gap-1 text-[11px]"
          data-testid="entities-semantic-search"
        >
          <span className="flex items-center gap-1 text-muted-foreground">
            <Sparkles className="h-3 w-3" />
            {t('entities.filters.semantic')}
          </span>
          <div className="relative">
            <input
              type="text"
              value={semanticInput}
              onChange={(e) =>
                handleFilterChange(() => setSemanticInput(e.target.value))
              }
              placeholder={t('entities.filters.semanticPlaceholder')}
              className="w-full rounded-md border bg-input py-1.5 px-2 text-xs outline-none focus:border-ring"
              data-testid="entities-filter-semantic"
            />
          </div>
        </label>
      )}

      <EntityStatusLegend />

      {isLoading && (
        <div
          className="text-[12px] text-muted-foreground"
          data-testid="entities-loading"
        >
          {t('entities.loading')}
        </div>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="entities-error"
        >
          {t('entities.loadFailed', { error: error.message })}
        </div>
      )}

      {!isLoading && !error && entities.length === 0 && (
        <p
          className="rounded-md border border-dashed px-3 py-6 text-center text-[12px] text-muted-foreground"
          data-testid="entities-empty"
        >
          {total === 0
            ? t('entities.empty')
            : t('entities.emptyForFilters')}
        </p>
      )}

      {!isLoading && !error && entities.length > 0 && (
        <>
          <EntitiesTable
            entities={entities}
            selectedEntityId={selectedEntityId}
            onSelect={setSelectedEntityId}
          />

          <div className="mt-3 flex items-center justify-between text-[11px]">
            <span
              className="text-muted-foreground"
              data-testid="entities-pagination-range"
            >
              {t('entities.pagination.range', {
                from: offset + 1,
                to: Math.min(offset + entities.length, total),
                total,
              })}
              {isFetching && (
                <span className="ml-2 text-muted-foreground/70">
                  {t('entities.pagination.refreshing')}
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!canPrev}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className="inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="entities-pagination-prev"
              >
                <ChevronLeft className="h-3 w-3" />
                {t('entities.pagination.prev')}
              </button>
              <button
                type="button"
                disabled={!canNext}
                onClick={() =>
                  setOffset(Math.min(maxOffset, offset + PAGE_SIZE))
                }
                className="inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="entities-pagination-next"
              >
                {t('entities.pagination.next')}
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          </div>
        </>
      )}

      <EntityDetailPanel
        open={!!selectedEntityId}
        onOpenChange={(o) => {
          if (!o) setSelectedEntityId(null);
        }}
        entityId={selectedEntityId}
        bookId={scopedBookId}
      />
    </div>
  );
}
