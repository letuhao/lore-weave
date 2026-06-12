import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BookOpen, Plus, Search, Filter, Trash2, Settings2, Layers, Sparkles, Languages, HelpCircle, Lightbulb, GitMerge } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { useGlossaryDisplayLanguage } from '@/features/glossary/hooks/useGlossaryDisplayLanguage';
import { type GlossaryEntitySummary, type EntityKind, type FilterState, defaultFilters } from '@/features/glossary/types';
import { getLanguageName } from '@/lib/languages';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState, ConfirmDialog } from '@/components/shared';
import { cn } from '@/lib/utils';
import { KindEditor } from './KindEditor';
import { GenreGroupsPanel } from '@/features/glossary/components/GenreGroupsPanel';
import { UnknownEntitiesPanel } from '@/features/glossary/components/UnknownEntitiesPanel';
import { AiSuggestionsPanel } from '@/features/glossary/components/AiSuggestionsPanel';
import { MergeCandidatePanel } from '@/features/glossary/components/MergeCandidatePanel';
import { EntityEditorModal } from '@/components/entity-editor';
import { ExtractionWizard } from '@/features/extraction/ExtractionWizard';
import { GlossaryTranslateWizard } from '@/features/glossary-translate/GlossaryTranslateWizard';
import { BookAssistantDock } from '@/features/chat/BookAssistantDock';

type GlossaryView = 'entities' | 'kinds' | 'genres' | 'unknown' | 'ai_suggestions' | 'merge_candidates';

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-amber-400/15 text-amber-400',
  active: 'bg-green-500/15 text-green-500',
  inactive: 'bg-muted text-muted-foreground',
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

export function GlossaryTab({ bookId, bookGenreTags = [], bookOriginalLanguage }: { bookId: string; bookGenreTags?: string[]; bookOriginalLanguage?: string }) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<FilterState>(defaultFilters);
  const [filterOpen, setFilterOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GlossaryEntitySummary | null>(null);
  const [createKindOpen, setCreateKindOpen] = useState(false);
  const [view, setView] = useState<GlossaryView>('entities');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [extractionOpen, setExtractionOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);

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
    queryKey: ['glossary-entities', bookId, filters, apiDisplayLanguage],
    queryFn: () =>
      glossaryApi.listEntities(
        bookId,
        { ...filters, limit: 100, offset: 0, displayLanguage: apiDisplayLanguage },
        accessToken!,
      ),
    enabled: !!accessToken && displayLangLoaded,
  });

  const { data: kinds = [] } = useQuery({
    queryKey: ['glossary-kinds'],
    queryFn: () => glossaryApi.getKinds(accessToken!),
    enabled: !!accessToken,
    staleTime: 10 * 60 * 1000, // kinds rarely change
  });

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
  const loading = entitiesLoading;
  const error = entitiesError ? (entitiesError as Error).message : '';

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['glossary-entities', bookId] });
    void queryClient.invalidateQueries({ queryKey: ['glossary-translation-languages', bookId] });
  };

  const visibleKinds = useMemo(
    () => kinds
      .filter((k) => !k.is_hidden)
      .filter((k) => {
        const tags = k.genre_tags ?? [];
        // Empty genre_tags or "universal" = show for all books
        if (tags.length === 0 || tags.includes('universal')) return true;
        // Otherwise, show if book has at least one matching genre
        return bookGenreTags.length === 0 || tags.some((tag) => bookGenreTags.includes(tag));
      })
      .sort((a, b) => a.sort_order - b.sort_order),
    [kinds, bookGenreTags],
  );

  const handleCreate = async (kindId: string) => {
    if (!accessToken) return;
    try {
      await glossaryApi.createEntity(bookId, kindId, accessToken);
      toast.success(t('glossary.created'));
      setCreateKindOpen(false);
      invalidate();
    } catch (e) {
      toast.error((e as Error).message);
    }
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

  if (view === 'kinds') {
    return <KindEditor bookId={bookId} onClose={() => setView('entities')} />;
  }
  if (view === 'genres') {
    return <GenreGroupsPanel bookId={bookId} kinds={kinds} onClose={() => setView('entities')} />;
  }
  if (view === 'unknown') {
    return <UnknownEntitiesPanel bookId={bookId} kinds={kinds} onClose={() => setView('entities')} />;
  }
  if (view === 'ai_suggestions') {
    return <AiSuggestionsPanel bookId={bookId} onClose={() => setView('entities')} />;
  }
  if (view === 'merge_candidates') {
    return <MergeCandidatePanel bookId={bookId} onClose={() => setView('entities')} />;
  }

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
              onChange={(e) => setDisplayLanguage(e.target.value)}
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
          {aiSuggestCount > 0 && (
            <button
              onClick={() => setView('ai_suggestions')}
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
              onClick={() => setView('merge_candidates')}
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
              onClick={() => setView('unknown')}
              data-testid="glossary-unknown-trigger"
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-500 hover:bg-amber-400/20 transition-colors"
            >
              <HelpCircle className="h-3.5 w-3.5" />
              {t('glossary.unknown')}
              <span className="rounded-full bg-amber-400/20 px-1.5 py-0.5 text-[10px] font-semibold">{unknownCount}</span>
            </button>
          )}
          <button
            onClick={() => setView('genres')}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Layers className="h-3.5 w-3.5" />
            {t('glossary.genres')}
          </button>
          <button
            onClick={() => setView('kinds')}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Settings2 className="h-3.5 w-3.5" />
            {t('glossary.kinds')}
          </button>
          <div className="relative">
            <button
              onClick={() => setCreateKindOpen(!createKindOpen)}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-3.5 w-3.5" />
              {t('glossary.new_entity')}
            </button>
            {createKindOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setCreateKindOpen(false)} />
                <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-md border bg-card shadow-lg">
                  {visibleKinds.map((k) => (
                    <button
                      key={k.kind_id}
                      onClick={() => void handleCreate(k.kind_id)}
                      className="flex w-full items-center gap-2 px-3 py-2 text-xs hover:bg-secondary transition-colors first:rounded-t-md last:rounded-b-md"
                    >
                      <span>{k.icon}</span>
                      <span>{k.name}</span>
                    </button>
                  ))}
                  {visibleKinds.length === 0 && (
                    <p className="px-3 py-2 text-xs text-muted-foreground">{t('glossary.no_kinds')}</p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Search + Filter bar */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={filters.searchQuery}
            onChange={(e) => setFilters((f) => ({ ...f, searchQuery: e.target.value }))}
            placeholder={t('glossary.search')}
            data-testid="glossary-search-input"
            className="w-full rounded-md border bg-background pl-9 pr-3 py-1.5 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
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
      </div>

      {/* Filter panel */}
      {filterOpen && (
        <div className="rounded-lg border bg-card p-3 space-y-3">
          <div className="space-y-1.5">
            <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">{t('glossary.kind_label')}</span>
            <div className="flex flex-wrap gap-1.5">
              {visibleKinds.map((k) => {
                const active = filters.kindCodes.includes(k.code);
                return (
                  <button
                    key={k.kind_id}
                    onClick={() => setFilters((f) => ({
                      ...f,
                      kindCodes: active ? f.kindCodes.filter((c) => c !== k.code) : [...f.kindCodes, k.code],
                    }))}
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
              {(['all', 'draft', 'active', 'inactive'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setFilters((f) => ({ ...f, status: s }))}
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
              onClick={() => setFilters(defaultFilters)}
              className="text-[10px] text-primary hover:underline"
            >
              {t('glossary.clear_filters')}
            </button>
          )}
        </div>
      )}

      {/* Entity list */}
      {entities.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title={t('glossary.empty.title')}
          description={t('glossary.empty.description')}
        />
      ) : (
        <div className="rounded-lg border divide-y">
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

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title={t('glossary.delete_confirm.title')}
        description={t('glossary.delete_confirm.description', { title: deleteTarget?.display_name || t('glossary.untitled') })}
        confirmLabel={t('glossary.delete_confirm.confirm')}
        variant="destructive"
        onConfirm={() => void handleDelete()}
      />

      {/* Entity Editor Modal */}
      {selectedEntityId && (() => {
        const selectedEntity = entities.find((e) => e.entity_id === selectedEntityId);
        const kindTags = kinds.find((k) => k.kind_id === selectedEntity?.kind_id)?.genre_tags ?? [];
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

      {/* P5: the book-scoped glossary assistant (floating dock → embedded chat). */}
      <BookAssistantDock bookId={bookId} />
    </div>
  );
}
