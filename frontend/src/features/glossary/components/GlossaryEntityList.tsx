import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BookOpen, Plus, Filter, Trash2, Layers, Sparkles, Languages, HelpCircle, Lightbulb, GitMerge, CheckCircle2, CircleSlash, XCircle, PencilLine, MapPin } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import { useGlossaryDisplayLanguage } from '../hooks/useGlossaryDisplayLanguage';
import { type GlossaryEntitySummary, type FilterState, type EntitySort, defaultFilters } from '../types';
import { useServerPagedList } from '@/components/pagination/useServerPagedList';
import { useDebouncedValue } from '@/features/raw-search/hooks/useDebouncedValue';
import { MatchSnippet } from './MatchSnippet';
import { EntityListBrowser } from './EntityListBrowser';
import { getLanguageName } from '@/lib/languages';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState, ConfirmDialog, FloatingActionBar, FloatingActionDivider } from '@/components/shared';
import { cn } from '@/lib/utils';
import { CreateEntityModal } from './tiering/CreateEntityModal';
import { useBookOntology } from '../hooks/useBookOntology';
import { EntityEditorModal } from '@/components/entity-editor';
import { ExtractionWizard } from '@/features/extraction/ExtractionWizard';
import { GlossaryTranslateWizard } from '@/features/glossary-translate/GlossaryTranslateWizard';
import { BatchTranslateDialog } from './BatchTranslateDialog';

/** The other 4 glossary capabilities, not yet each their own dock panel (13_glossary_panels.md
 * Phase B — tracked, not a silent gap). The caller (GlossaryTab page / GlossaryPanel dock panel)
 * decides how to open them; this component only ever asks via `onOpenView`. */
export type OtherGlossaryView = 'ontology' | 'unknown' | 'ai_suggestions' | 'merge_candidates';

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-amber-400/15 text-amber-400',
  active: 'bg-green-500/15 text-green-500',
  inactive: 'bg-muted text-muted-foreground',
  rejected: 'bg-destructive/15 text-destructive',
};

function KindBadge({ kind }: { kind: GlossaryEntitySummary['kind'] }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
      style={{ backgroundColor: kind.color + '18', color: kind.color }}
    >
      <span>{kind.icon}</span>
      {kind.name}
    </span>
  );
}

interface GlossaryEntityListProps {
  bookId: string;
  bookGenreTags?: string[];
  bookOriginalLanguage?: string;
  /** DOCK-8 launcher seam — routes to the 4 not-yet-dockable capabilities. */
  onOpenView: (view: OtherGlossaryView) => void;
}

/** The entity list/search/filter/bulk-actions capability (13_glossary_panels.md A3) — extracted
 * from GlossaryTab so it can be a thin dock-panel view (GlossaryPanel) AND the classic page
 * (GlossaryTab) without forking the ~500 lines between them (DOCK-2). Owns NO navigation of its
 * own — `onOpenView` is the only way out to a sibling capability. */
export function GlossaryEntityList({ bookId, bookGenreTags = [], bookOriginalLanguage, onOpenView }: GlossaryEntityListProps) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [filterOpen, setFilterOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GlossaryEntitySummary | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [extractionOpen, setExtractionOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);
  const [batchTranslateOpen, setBatchTranslateOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  // Default sort = appearance (chapter-link count) DESC, so the most-present
  // entities (main characters etc.) surface first instead of sinking by recency.
  const [sort, setSort] = useState<EntitySort>('links');
  const [searchMode, setSearchMode] = useState<'simple' | 'raw'>('simple');
  const paged = useServerPagedList(10);
  // Debounce the search box so we hit the BE once the user pauses, not per keystroke.
  const debouncedSearch = useDebouncedValue(filters.searchQuery, 300);

  const { displayLanguage, setDisplayLanguage, apiDisplayLanguage, loaded: displayLangLoaded } =
    useGlossaryDisplayLanguage(bookId, bookOriginalLanguage);

  const { data: translationLangsData } = useQuery({
    queryKey: ['glossary-translation-languages', bookId],
    queryFn: () => glossaryApi.listTranslationLanguages(bookId, accessToken!),
    enabled: !!accessToken,
    staleTime: 60 * 1000,
  });

  const languageOptions = useMemo(() => {
    const opts: { code: string; label: string }[] = [];
    if (bookOriginalLanguage) {
      opts.push({
        code: bookOriginalLanguage,
        label: t('glossary.display_language_original', { lang: getLanguageName(bookOriginalLanguage) }),
      });
    } else {
      opts.push({
        code: '',
        label: t('glossary.display_language_as_authored'),
      });
    }
    const seen = new Set(opts.map((o) => o.code));
    for (const code of translationLangsData?.languages ?? []) {
      if (code === bookOriginalLanguage || seen.has(code)) continue;
      seen.add(code);
      opts.push({ code, label: getLanguageName(code) });
    }
    if (displayLanguage && !seen.has(displayLanguage)) {
      opts.push({ code: displayLanguage, label: getLanguageName(displayLanguage) });
    }
    return opts;
  }, [bookOriginalLanguage, displayLanguage, t, translationLangsData?.languages]);

  const { data: entityData, isLoading: entitiesLoading, error: entitiesError } = useQuery({
    queryKey: [
      'glossary-entities', bookId,
      filters.kindCodes, filters.status, debouncedSearch, searchMode, sort,
      paged.offset, paged.limit, apiDisplayLanguage,
    ],
    queryFn: () =>
      glossaryApi.listEntities(
        bookId,
        {
          ...filters,
          searchQuery: debouncedSearch,
          searchMode,
          sort,
          limit: paged.limit,
          offset: paged.offset,
          displayLanguage: apiDisplayLanguage,
        },
        accessToken!,
      ),
    enabled: !!accessToken && displayLangLoaded,
    placeholderData: (prev) => prev, // keep the current page visible while the next loads
  });

  // Book-tier ontology drives the kind filter + count (G6f): entities are book-kind
  // scoped post-G4, so the filter must list THIS book's adopted kinds — not the global
  // system kinds (D-GKA-FILTER-BOOKKINDS). Shares the ['glossary-ontology', bookId]
  // query with the Ontology screens, so it's one fetch.
  const ontology = useBookOntology(bookId);
  const kinds = ontology.ontology.kinds;

  // Unknown-kind review queue count — drives the conditional triage button + badge.
  // Shares the ['glossary-unknown', bookId] key with UnknownEntitiesPanel (deduped).
  const { data: unknownData } = useQuery({
    queryKey: ['glossary-unknown', bookId],
    queryFn: () => glossaryApi.listUnknownEntities(bookId, accessToken!),
    enabled: !!accessToken,
    staleTime: 60 * 1000, // badge-only read; resolve actions invalidate explicitly
  });
  const unknownCount = unknownData?.total ?? 0;

  // AI-suggestions inbox count — drives the conditional trigger + badge.
  // Shares the ['glossary-ai-suggestions', bookId] key with the panel/hook.
  const { data: aiSuggestData } = useQuery({
    queryKey: ['glossary-ai-suggestions', bookId],
    queryFn: () => glossaryApi.listAiSuggestions(bookId, accessToken!),
    enabled: !!accessToken,
    staleTime: 60 * 1000,
  });
  const aiSuggestCount = aiSuggestData?.total ?? 0;

  // Merge-candidate inbox count (mui #1c) — conditional trigger + badge.
  // Shares ['glossary-merge-candidates', bookId] with the panel/hook.
  const { data: mergeCandData } = useQuery({
    queryKey: ['glossary-merge-candidates', bookId],
    queryFn: () => glossaryApi.listMergeCandidates(bookId, accessToken!),
    enabled: !!accessToken,
    staleTime: 60 * 1000,
  });
  const mergeCandCount = mergeCandData?.candidates.length ?? 0;

  const entities = entityData?.items ?? [];
  const total = entityData?.total ?? 0;
  const { pageCount, safePage, start, end } = paged.pageInfo(total);
  const loading = entitiesLoading;
  const error = entitiesError ? (entitiesError as Error).message : '';

  // Filter/sort/search changes reset to page 0 (the old offset is meaningless on a
  // new result set). Done in handlers, not an effect — page-reset is an event
  // reaction (FE rule). debouncedSearch is reset via the search box's onChange.
  const updateFilters = (next: Partial<FilterState>) => {
    setFilters((f) => ({ ...f, ...next }));
    paged.reset();
  };
  const changeSort = (s: EntitySort) => {
    setSort(s);
    paged.reset();
  };
  const toggleSearchMode = () => {
    const next = searchMode === 'raw' ? 'simple' : 'raw';
    setSearchMode(next);
    // Raw search defaults to relevance ranking; leaving raw drops back to the
    // default appearance sort (only if still on relevance — keep any manual pick).
    setSort((s) => (next === 'raw' ? 'relevance' : s === 'relevance' ? 'links' : s));
    paged.reset();
  };

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['glossary-entities', bookId] });
    void queryClient.invalidateQueries({ queryKey: ['glossary-translation-languages', bookId] });
  };

  // Book kinds are already book-scoped, so no genre_tags filtering is needed (the old
  // flat model filtered system kinds by genre_tags; that column was retired in G4).
  const visibleKinds = useMemo(
    () => kinds.filter((k) => !k.is_hidden).sort((a, b) => a.sort_order - b.sort_order),
    [kinds],
  );

  // G6f: creation moved into CreateEntityModal (post-G4 a kind is a book_kind_id, so the
  // tiered form picks a BOOK kind and writes its genre override + attribute values). The
  // new entity surfaces in the list on invalidate; the user opens it to keep editing.
  const handleEntityCreated = (_entityId: string) => {
    setCreateOpen(false);
    invalidate();
  };

  const handleDelete = async () => {
    if (!accessToken || !deleteTarget) return;
    try {
      await glossaryApi.deleteEntity(bookId, deleteTarget.entity_id, accessToken);
      toast.success(t('glossary.deleted'));
      setDeleteTarget(null);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  // ── Multi-select (bulk status) ─────────────────────────────────────────────
  // Selection acts on what's visible: select-all/clear + the bulk action all
  // operate on the currently-filtered `entities`, so "filter draft → select all
  // → activate" does exactly what the user sees.
  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  // The bulk action targets ALL selected ids — including ones not on the loaded
  // page (the "select all N" button below loop-fetches them) — so activation isn't
  // silently capped at the first 100 rows on a large book.
  const allLoadedSelected = entities.length > 0 && entities.every((e) => selectedIds.has(e.entity_id));
  const hasMoreThanLoaded = total > entities.length;
  const _BULK_CAP = 1000; // matches the server's entity_ids cap
  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allLoadedSelected) {
        entities.forEach((e) => next.delete(e.entity_id));
      } else {
        entities.forEach((e) => next.add(e.entity_id));
      }
      return next;
    });
  };
  const clearSelection = () => setSelectedIds(new Set());

  // Gmail-style "select all N matching the current filter/search" — loop-fetches
  // EVERY matching id across all pages (the visible list is one page), so a bulk
  // action isn't capped at the current page. Honors the active search/sort.
  const selectAllMatching = async () => {
    if (!accessToken) return;
    setBulkBusy(true);
    try {
      const ids = new Set<string>();
      const fetchSize = 200;
      for (let offset = 0; offset < total && ids.size < _BULK_CAP; offset += fetchSize) {
        const page = await glossaryApi.listEntities(
          bookId,
          { ...filters, searchQuery: debouncedSearch, searchMode, sort, limit: fetchSize, offset, displayLanguage: apiDisplayLanguage },
          accessToken,
        );
        if (page.items.length === 0) break;
        for (const e of page.items) {
          if (ids.size >= _BULK_CAP) break;
          ids.add(e.entity_id);
        }
      }
      setSelectedIds(ids);
      if (total > _BULK_CAP) toast.info(t('glossary.bulk.cap_note', { cap: _BULK_CAP }));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  };

  const handleBulkStatus = async (status: 'active' | 'inactive' | 'rejected') => {
    const ids = [...selectedIds];
    if (!accessToken || ids.length === 0) return;
    setBulkBusy(true);
    try {
      const { updated } = await glossaryApi.bulkSetStatus(bookId, status, ids, accessToken);
      toast.success(t('glossary.bulk.done', { count: updated, status: t(`glossary.status.${status}`) }));
      clearSelection();
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  };

  // Bulk soft-delete the selected entities (clean up extraction duplicates, #40).
  // Gated behind a destructive confirm; the server ignores foreign/already-deleted
  // ids, so `deleted` is the real count (the partial-success report).
  const handleBulkDelete = async () => {
    const ids = [...selectedIds];
    if (!accessToken || ids.length === 0) return;
    setBulkBusy(true);
    try {
      const { deleted } = await glossaryApi.bulkDeleteEntities(bookId, ids, accessToken);
      toast.success(t('glossary.bulk.deleted', { count: deleted }));
      setBulkDeleteOpen(false);
      clearSelection();
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  };

  const handleToggleAlive = async (entity: GlossaryEntitySummary) => {
    if (!accessToken) return;
    try {
      await glossaryApi.patchEntity(bookId, entity.entity_id, { alive: !entity.alive }, accessToken);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const activeFilterCount = (filters.kindCodes.length > 0 ? 1 : 0) + (filters.status !== 'all' ? 1 : 0);

  if (!displayLangLoaded || (loading && entities.length === 0)) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return <div className="p-6 text-sm text-destructive">{error}</div>;
  }

  // Sort options for the browser dropdown; "relevance" only makes sense in raw mode.
  const sortOptions: { value: string; label: string }[] = [
    ...(searchMode === 'raw' ? [{ value: 'relevance', label: t('glossary.sort.relevance') }] : []),
    { value: 'links', label: t('glossary.sort.links') },
    { value: 'evidence', label: t('glossary.sort.evidence') },
    { value: 'updated_at', label: t('glossary.sort.updated_at') },
    { value: 'created_at', label: t('glossary.sort.created_at') },
    { value: 'name', label: t('glossary.sort.name') },
    { value: 'name_desc', label: t('glossary.sort.name_desc') },
    { value: 'kind', label: t('glossary.sort.kind') },
    { value: 'status', label: t('glossary.sort.status') },
    { value: 'alive', label: t('glossary.sort.alive') },
  ];

  return (
    <div className="space-y-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t('glossary.header')}</h3>
          <p className="text-xs text-muted-foreground">
            {t('glossary.entity_count', { count: total })}
            {visibleKinds.length > 0 && ` · ${t('glossary.kind_count', { count: visibleKinds.length })}`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <div className="flex items-center gap-1.5">
            <label htmlFor="glossary-display-lang" className="text-[10px] text-muted-foreground whitespace-nowrap">
              {t('glossary.display_language')}
            </label>
            <select
              id="glossary-display-lang"
              data-testid="glossary-display-language"
              value={displayLanguage}
              onChange={(e) => { setDisplayLanguage(e.target.value); paged.reset(); }}
              className="h-8 rounded-md border bg-background px-2 text-[11px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            >
              {languageOptions.map((opt) => (
                <option key={opt.code} value={opt.code}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={() => setExtractionOpen(true)}
            data-testid="glossary-extract-trigger"
            className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {t('glossary.extract')}
          </button>
          <button
            onClick={() => setTranslateOpen(true)}
            data-testid="glossary-translate-trigger"
            className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
          >
            <Languages className="h-3.5 w-3.5" />
            {t('glossary.translate')}
          </button>
          <button
            onClick={() => setBatchTranslateOpen(true)}
            data-testid="glossary-batch-translate-trigger"
            title={t('glossary.batch_translate_hint', { defaultValue: 'Type target names for many entities by hand (drafts; never overwrites verified)' })}
            className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
          >
            <PencilLine className="h-3.5 w-3.5" />
            {t('glossary.batch_translate', { defaultValue: 'Manual translate' })}
          </button>
          {aiSuggestCount > 0 && (
            <button
              onClick={() => onOpenView('ai_suggestions')}
              data-testid="glossary-ai-suggestions-trigger"
              className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
            >
              <Lightbulb className="h-3.5 w-3.5" />
              {t('glossary.ai_suggestions')}
              <span className="rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold">{aiSuggestCount}</span>
            </button>
          )}
          {mergeCandCount > 0 && (
            <button
              onClick={() => onOpenView('merge_candidates')}
              data-testid="glossary-merge-candidates-trigger"
              className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
            >
              <GitMerge className="h-3.5 w-3.5" />
              {t('glossary.merge_candidates')}
              <span className="rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold">{mergeCandCount}</span>
            </button>
          )}
          {unknownCount > 0 && (
            <button
              onClick={() => onOpenView('unknown')}
              data-testid="glossary-unknown-trigger"
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-500 hover:bg-amber-400/20 transition-colors"
            >
              <HelpCircle className="h-3.5 w-3.5" />
              {t('glossary.unknown')}
              <span className="rounded-full bg-amber-400/20 px-1.5 py-0.5 text-[10px] font-semibold">{unknownCount}</span>
            </button>
          )}
          <button
            onClick={() => onOpenView('ontology')}
            data-testid="glossary-ontology-trigger"
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Layers className="h-3.5 w-3.5" />
            {t('glossary.ontology')}
          </button>
          <button
            onClick={() => setCreateOpen(true)}
            data-testid="glossary-new-entity"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" />
            {t('glossary.new_entity')}
          </button>
        </div>
      </div>

      <EntityListBrowser
        searchValue={filters.searchQuery}
        onSearchChange={(v) => updateFilters({ searchQuery: v })}
        searchMode={searchMode}
        onToggleSearchMode={toggleSearchMode}
        sort={sort}
        onSortChange={(s) => changeSort(s as EntitySort)}
        sortOptions={sortOptions}
        total={total}
        paged={paged}
        pageInfo={{ pageCount, safePage, start, end }}
        filterControl={
          <button
            onClick={() => setFilterOpen(!filterOpen)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
              activeFilterCount > 0
                ? 'border-primary/40 text-primary hover:bg-primary/10'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
            )}
          >
            <Filter className="h-3.5 w-3.5" />
            {activeFilterCount > 0 ? t('glossary.filter_count', { count: activeFilterCount }) : t('glossary.filter')}
          </button>
        }
        filterPanel={filterOpen ? (
          <div className="rounded-lg border bg-card p-3 space-y-3">
            <div className="space-y-1.5">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{t('glossary.kind_label')}</span>
              <div className="flex flex-wrap gap-1.5">
                {visibleKinds.map((k) => {
                  const active = filters.kindCodes.includes(k.code);
                  return (
                    <button
                      key={k.book_kind_id}
                      onClick={() => updateFilters({
                        kindCodes: active ? filters.kindCodes.filter((c) => c !== k.code) : [...filters.kindCodes, k.code],
                      })}
                      className={cn(
                        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors',
                        active ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:text-foreground',
                      )}
                    >
                      <span>{k.icon}</span> {k.name}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1.5">
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{t('glossary.status_label')}</span>
              <div className="flex gap-1.5">
                {(['all', 'draft', 'active', 'inactive', 'rejected'] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => updateFilters({ status: s })}
                    className={cn(
                      'rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors',
                      filters.status === s ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {s === 'all' ? t('glossary.status_all') : t(`glossary.status.${s}`)}
                  </button>
                ))}
              </div>
            </div>
            {activeFilterCount > 0 && (
              <button
                onClick={() => { setFilters(defaultFilters); paged.reset(); }}
                className="text-[10px] text-primary hover:underline"
              >
                {t('glossary.clear_filters')}
              </button>
            )}
          </div>
        ) : null}
      >
      {/* Entity list */}
      {entities.length === 0 ? (
        total > 0 ? (
          // An out-of-range page (e.g. rows deleted while paged deep) — total>0 but
          // this offset is empty. Offer a jump back rather than a false "empty".
          <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
            {t('glossary.page_empty')}{' '}
            <button onClick={() => paged.setPage(0)} className="text-primary hover:underline">
              {t('glossary.page_empty_first')}
            </button>
          </div>
        ) : (
          <EmptyState
            icon={BookOpen}
            title={t('glossary.empty.title')}
            description={t('glossary.empty.description')}
          />
        )
      ) : (
        <div className="rounded-lg border divide-y">
          {/* Select-all bar — drives the bulk status actions on the filtered list */}
          <div className="flex items-center gap-2 px-4 py-2 bg-card/30">
            <input
              type="checkbox"
              checked={allLoadedSelected}
              onChange={toggleSelectAll}
              aria-label={t('glossary.bulk.select_all')}
              className="h-3.5 w-3.5 rounded border-border accent-primary cursor-pointer"
            />
            <span className="text-[11px] text-muted-foreground">
              {selectedIds.size > 0
                ? t('glossary.bulk.selected', { count: selectedIds.size })
                : t('glossary.bulk.select_all')}
            </span>
            {/* When the list is capped at the loaded page, offer to select every
                matching entity (loop-fetch) so activation isn't silently limited. */}
            {hasMoreThanLoaded && allLoadedSelected && selectedIds.size < total && (
              <button
                onClick={() => void selectAllMatching()}
                disabled={bulkBusy}
                className="text-[11px] text-primary hover:underline disabled:opacity-50"
              >
                {t('glossary.bulk.select_all_matching', { count: total })}
              </button>
            )}
          </div>
          {entities.map((e) => (
            <div
              key={e.entity_id}
              onClick={() => setSelectedEntityId(e.entity_id)}
              data-testid="glossary-entity-row"
              className={cn(
                'flex items-center gap-3 px-4 py-3 hover:bg-card/50 transition-colors group cursor-pointer',
                selectedEntityId === e.entity_id && 'bg-primary/5 border-l-2 border-l-primary',
              )}
            >
              <input
                type="checkbox"
                checked={selectedIds.has(e.entity_id)}
                onClick={(ev) => ev.stopPropagation()}
                onChange={() => toggleSelect(e.entity_id)}
                aria-label={t('glossary.bulk.select_row')}
                className="h-3.5 w-3.5 shrink-0 rounded border-border accent-primary cursor-pointer"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="text-sm font-medium truncate"
                    title={
                      apiDisplayLanguage && !e.display_name_translation
                        ? t('glossary.fallback_to_original')
                        : undefined
                    }
                  >
                    {e.display_name || t('glossary.untitled')}
                  </span>
                  <KindBadge kind={e.kind} />
                  <span className={cn('rounded-full px-1.5 py-0.5 text-[9px] font-medium', STATUS_COLORS[e.status])}>
                    {t(`glossary.status.${e.status}`)}
                  </span>
                  {e.scope_label && (
                    <span
                      className="inline-flex items-center gap-0.5 rounded-full bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-medium text-violet-400"
                      title={t('glossary.scope_label_title')}
                    >
                      <MapPin className="h-2.5 w-2.5" />
                      {e.scope_label}
                    </span>
                  )}
                  {e.alive != null && (
                    <button
                      onClick={(ev) => { ev.stopPropagation(); void handleToggleAlive(e); }}
                      className={cn(
                        'rounded-full px-1.5 py-0.5 text-[9px] font-medium transition-colors',
                        e.alive
                          ? 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                          : 'bg-muted text-muted-foreground hover:bg-muted/80',
                      )}
                      title={e.alive ? t('glossary.alive_title') : t('glossary.dead_title')}
                    >
                      {e.alive ? t('glossary.alive') : t('glossary.dead')}
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-[10px] text-muted-foreground">
                  {e.chapter_link_count > 0 && <span>{t('glossary.chapter_count', { count: e.chapter_link_count })}</span>}
                  {e.translation_count > 0 && <span>{t('glossary.translation_count', { count: e.translation_count })}</span>}
                  {e.evidence_count > 0 && <span>{t('glossary.evidence_count', { count: e.evidence_count })}</span>}
                  {e.tags.length > 0 && <span>{e.tags.join(', ')}</span>}
                </div>
                {/* Raw-search: show which field matched + a highlighted snippet. */}
                {searchMode === 'raw' && e.match && (
                  <div className="mt-1"><MatchSnippet match={e.match} /></div>
                )}
              </div>
              <button
                onClick={() => setDeleteTarget(e)}
                className="opacity-0 group-hover:opacity-100 max-md:opacity-100 rounded p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                title={t('glossary.delete')}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      </EntityListBrowser>

      {/* Bulk status action bar */}
      <FloatingActionBar visible={selectedIds.size > 0}>
        <span className="text-sm font-medium">{t('glossary.bulk.selected', { count: selectedIds.size })}</span>
        <FloatingActionDivider />
        <button
          onClick={() => void handleBulkStatus('active')}
          disabled={bulkBusy}
          className="inline-flex items-center gap-1.5 rounded-full bg-green-500/90 px-4 py-1.5 text-xs font-medium text-white hover:bg-green-500 disabled:opacity-50 transition-colors"
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          {t('glossary.bulk.activate')}
        </button>
        <button
          onClick={() => void handleBulkStatus('inactive')}
          disabled={bulkBusy}
          className="inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-50 transition-colors"
        >
          <CircleSlash className="h-3.5 w-3.5" />
          {t('glossary.bulk.deactivate')}
        </button>
        <button
          onClick={() => void handleBulkStatus('rejected')}
          disabled={bulkBusy}
          className="inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-50 transition-colors"
        >
          <XCircle className="h-3.5 w-3.5" />
          {t('glossary.bulk.reject')}
        </button>
        <button
          onClick={() => setBulkDeleteOpen(true)}
          disabled={bulkBusy}
          className="inline-flex items-center gap-1.5 rounded-full bg-destructive/90 px-4 py-1.5 text-xs font-medium text-white hover:bg-destructive disabled:opacity-50 transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" />
          {t('glossary.bulk.delete')}
        </button>
        <button onClick={clearSelection} className="text-xs text-muted-foreground hover:text-foreground transition-colors">
          {t('glossary.bulk.clear')}
        </button>
      </FloatingActionBar>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title={t('glossary.delete_confirm.title')}
        description={t('glossary.delete_confirm.description', { title: deleteTarget?.display_name || t('glossary.untitled') })}
        confirmLabel={t('glossary.delete_confirm.confirm')}
        variant="destructive"
        onConfirm={() => void handleDelete()}
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title={t('glossary.bulk.delete_confirm.title', { count: selectedIds.size })}
        description={t('glossary.bulk.delete_confirm.description', { count: selectedIds.size })}
        confirmLabel={t('glossary.bulk.delete')}
        variant="destructive"
        loading={bulkBusy}
        onConfirm={() => void handleBulkDelete()}
      />

      {/* Entity Editor Modal */}
      {selectedEntityId && (() => {
        const selectedEntity = entities.find((e) => e.entity_id === selectedEntityId);
        // kindGenreTags drove old flat-model genre filtering; genre_tags was retired in
        // G4 and entities are book-kind scoped, so there are no kind-level genre tags now.
        const kindTags: string[] = [];
        return (
          <EntityEditorModal
            bookId={bookId}
            entityId={selectedEntityId}
            bookGenreTags={bookGenreTags}
            kindGenreTags={kindTags}
            bookOriginalLanguage={bookOriginalLanguage}
            displayLanguage={displayLanguage}
            onClose={() => setSelectedEntityId(null)}
            onSaved={() => invalidate()}
            onDelete={() => {
              setDeleteTarget(selectedEntity ?? null);
            }}
          />
        );
      })()}

      {createOpen && (
        <CreateEntityModal
          bookId={bookId}
          onClose={() => setCreateOpen(false)}
          onCreated={handleEntityCreated}
        />
      )}

      <ExtractionWizard
        open={extractionOpen}
        onOpenChange={setExtractionOpen}
        bookId={bookId}
        mode="batch"
        onComplete={() => invalidate()}
      />

      <GlossaryTranslateWizard
        open={translateOpen}
        onOpenChange={setTranslateOpen}
        bookId={bookId}
        bookOriginalLanguage={bookOriginalLanguage}
        onComplete={() => invalidate()}
      />

      {/* S4 — manual per-entity batch translate (complements the auto wizard above). */}
      {batchTranslateOpen && (
        <BatchTranslateDialog
          bookId={bookId}
          onClose={() => {
            setBatchTranslateOpen(false);
            invalidate();
          }}
        />
      )}
    </div>
  );
}
