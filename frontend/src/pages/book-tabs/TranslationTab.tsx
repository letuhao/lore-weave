import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Languages, Check, Clock, AlertCircle, Loader2, Plus, Filter, X, Sparkles, History, RefreshCw } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { translationApi, type BookCoverageResponse, type CoverageCell } from '@/features/translation/api';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState, FloatingActionBar, FloatingActionDivider } from '@/components/shared';
import { cn } from '@/lib/utils';
import { getLanguageName } from '@/lib/languages';
import { usePagedList } from '@/components/pagination/usePagedList';
import { Pager } from '@/components/pagination/Pager';
import { TranslateModal } from './TranslateModal';
import { TranslationErrorState } from '@/features/translation/components/TranslationErrorState';
import { SegmentDrilldownModal } from '@/features/translation/components/SegmentDrilldownModal';
import { ExtractionWizard } from '@/features/extraction/ExtractionWizard';

/** Rows per page in the coverage matrix — D4: one row per chapter is unbounded (2000+ books). */
const MATRIX_PAGE_SIZE = 100;

function cellContent(cell: CoverageCell | undefined, t: TFunction) {
  if (!cell || cell.version_count === 0) {
    return <span className="text-[11px] text-muted-foreground">—</span>;
  }
  const s = cell.latest_status;
  if (s === 'completed' && cell.has_active) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-green-500">
        <Check className="h-3 w-3" strokeWidth={2.5} />
        {t('matrix.cell_done')}
      </span>
    );
  }
  if (s === 'completed') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-green-500/60">
        <Check className="h-3 w-3" strokeWidth={2.5} />
        {t('matrix.cell_done')}
      </span>
    );
  }
  if (s === 'running') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-blue-400">
        <Loader2 className="h-3 w-3 animate-spin" />
        {t('matrix.cell_running')}
      </span>
    );
  }
  if (s === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-destructive">
        <X className="h-3 w-3" strokeWidth={2.5} />
        {t('matrix.cell_failed')}
      </span>
    );
  }
  if (s === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-amber-400">
        <Clock className="h-3 w-3" />
        {t('matrix.cell_pending')}
      </span>
    );
  }
  return <span className="text-[11px] text-muted-foreground">—</span>;
}

function cellBg(cell: CoverageCell | undefined): string {
  if (!cell || cell.version_count === 0) return '';
  const s = cell.latest_status;
  if (s === 'completed') return 'bg-green-500/[0.08]';
  if (s === 'running') return 'bg-blue-400/[0.06]';
  if (s === 'failed') return 'bg-destructive/[0.06]';
  if (s === 'pending') return 'bg-amber-400/[0.06]';
  return '';
}

function cellStatus(cell: CoverageCell | undefined): string | null {
  if (!cell || cell.version_count === 0) return null;
  return cell.latest_status ?? null;
}

/** Languages that have at least one translation across any chapter */
function languagesWithData(coverage: BookCoverageResponse): Set<string> {
  const active = new Set<string>();
  for (const row of coverage.coverage) {
    for (const [lang, cell] of Object.entries(row.languages)) {
      if (cell.version_count > 0) active.add(lang);
    }
  }
  return active;
}

/**
 * M6b-2: which chapters have a glossary-stale translation in any visible language,
 * plus the total count of stale (chapter × language) cells. Drives the "N affected"
 * legend + the "Select affected" quick-action (→ existing translate flow).
 */
export function staleChapterIds(
  coverage: BookCoverageResponse,
  visibleLangs: string[],
): { ids: Set<string>; cells: number } {
  const ids = new Set<string>();
  let cells = 0;
  for (const row of coverage.coverage) {
    for (const lang of visibleLangs) {
      if (row.languages[lang]?.is_glossary_stale) {
        cells++;
        ids.add(row.chapter_id);
      }
    }
  }
  return { ids, cells };
}

export function TranslationTab({
  bookId,
  onManageVersions,
}: {
  bookId: string;
  /** DOCK-7 seam: when provided (the `translation` studio panel), a matrix-cell click routes
   * through this callback (host.openPanel('translation-versions', ...)) instead of navigating —
   * the studio never unmounts itself to satisfy one panel's link. The classic route page (no
   * studio host available) omits this prop and falls back to the original route navigation. */
  onManageVersions?: (chapterId: string, lang: string) => void;
}) {
  const { t } = useTranslation('translation');
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedLangs, setSelectedLangs] = useState<Set<string> | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);
  // T8/D6: when the modal is opened from the selection (FloatingActionBar), it inherits the
  // ticked chapters + the language column; the header/empty-state CTAs open it UNSCOPED (D1).
  const [translateScoped, setTranslateScoped] = useState(false);
  const [extractionOpen, setExtractionOpen] = useState(false);
  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set());
  // T2-M3: per-segment drill-down target (chapter × language), null when closed.
  const [drillTarget, setDrillTarget] = useState<{ chapterId: string; lang: string; title?: string } | null>(null);

  const { data: coverageData, isLoading: coverageLoading, error: coverageError, refetch: refetchCoverage } = useQuery({
    queryKey: ['translation-coverage', bookId],
    queryFn: () => translationApi.getBookCoverage(accessToken!, bookId),
    enabled: !!accessToken,
  });

  // C: loop-fetch ALL active chapters (the backend clamps a single request to 100, so
  // a >100-chapter book would otherwise lose titles past the first page).
  const { data: chaptersData, isLoading: chaptersLoading, error: chaptersError, refetch: refetchChapters } = useQuery({
    queryKey: ['chapters', bookId, 'all'],
    queryFn: async () => {
      const items: Chapter[] = [];
      const pageSize = 100;
      for (let offset = 0; ; offset += pageSize) {
        const r = await booksApi.listChapters(accessToken!, bookId, {
          lifecycle_state: 'active', limit: pageSize, offset,
        });
        items.push(...r.items);
        if (r.items.length < pageSize || items.length >= (r.total ?? Infinity)) break;
      }
      return { items, total: items.length };
    },
    enabled: !!accessToken,
  });

  // T9/D10-C: the caller's effective grant, so the translate affordance is DISABLED-with-reason
  // for a view-only collaborator (who would otherwise be refused at submit with a late 403),
  // rather than hidden (indistinguishable from the T1 no-button bug).
  const { data: book } = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId),
    enabled: !!accessToken,
  });
  // Fail OPEN when the grant is unknown/loading (older server, in-flight) so we never disable
  // the button for everyone — only an explicit view/none grant gates it.
  const canEdit = book?.access_level ? ['owner', 'manage', 'edit'].includes(book.access_level) : true;

  const coverage = coverageData ?? null;
  const chapters = chaptersData?.items ?? [];
  // T4 + T10 + D9: a coverage OR chapter-list failure is a real error surfaced with a typed
  // message + Retry — never rendered as a raw proxy string, and never as an empty book.
  const queryError = coverageError ?? chaptersError;
  const loading = !queryError && (coverageLoading || chaptersLoading);
  const retryAll = () => { void refetchCoverage(); void refetchChapters(); };

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['translation-coverage', bookId] });
    // T2-M3: keep the per-cell "N changed" badges (segment-coverage) in sync too.
    queryClient.invalidateQueries({ queryKey: ['segment-coverage', bookId] });
  };

  const allLanguages = coverage?.known_languages ?? [];
  const autoLangs = useMemo(() => coverage ? languagesWithData(coverage) : new Set<string>(), [coverage]);
  const visibleLangs = useMemo(() => {
    if (selectedLangs) return allLanguages.filter((l) => selectedLangs.has(l));
    const withData = allLanguages.filter((l) => autoLangs.has(l));
    return withData.length > 0 ? withData : allLanguages;
  }, [allLanguages, selectedLangs, autoLangs]);

  // T2-M3: per (chapter, language) "needs re-translation" counts (dirty ∪ glossary-
  // stale), one fetch per visible language. Map: chapter_id → lang → needs_count.
  const { data: needsMap } = useQuery({
    queryKey: ['segment-coverage', bookId, visibleLangs.join(',')],
    queryFn: async () => {
      const map: Record<string, Record<string, number>> = {};
      await Promise.all(visibleLangs.map(async (lang) => {
        const r = await translationApi.getSegmentCoverage(accessToken!, bookId, lang);
        for (const c of r.chapters) {
          (map[c.chapter_id] ??= {})[lang] = c.needs_count;
        }
      }));
      return map;
    },
    enabled: !!accessToken && visibleLangs.length > 0,
  });

  const toggleLang = (lang: string) => {
    setSelectedLangs((prev) => {
      const next = new Set(prev ?? autoLangs);
      if (next.has(lang)) next.delete(lang); else next.add(lang);
      return next;
    });
  };

  const resetFilter = () => { setSelectedLangs(null); setFilterOpen(false); };

  // D3: the matrix renders one row per CHAPTER (in reading order), left-joined onto coverage —
  // an untranslated chapter has no coverage row but must still appear + be selectable (T2).
  const coverageByChapter = useMemo(
    () => new Map((coverage?.coverage ?? []).map((r) => [r.chapter_id, r])),
    [coverage],
  );
  const chapterSet = useMemo(() => new Set(chapters.map((c) => c.chapter_id)), [chapters]);
  const rows = useMemo(
    () =>
      [...chapters]
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
        .map((ch) => ({ ch, languages: coverageByChapter.get(ch.chapter_id)?.languages ?? {} })),
    [chapters, coverageByChapter],
  );
  // D5: coverage rows whose chapter is no longer active (trashed but still translated) are
  // surfaced as a footnote, never silently dropped by the left-join.
  const orphanCount = useMemo(
    () => (coverage?.coverage ?? []).filter((r) => !chapterSet.has(r.chapter_id)).length,
    [coverage, chapterSet],
  );
  // D4: one row per chapter is unbounded — page it (selection is by id, so it survives paging).
  const { page, setPage, pageCount, start, pageItems: pageRows } = usePagedList(rows, MATRIX_PAGE_SIZE);

  // Chapter selection
  const toggleChapter = (id: string) => {
    setSelectedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  // D4: select-all covers EVERY chapter (not just the visible page), and the label says so.
  const allChapterIds = useMemo(() => chapters.map((c) => c.chapter_id), [chapters]);
  const toggleAllChapters = () => {
    setSelectedChapters((prev) => (prev.size === allChapterIds.length ? new Set() : new Set(allChapterIds)));
  };
  const clearSelection = () => setSelectedChapters(new Set());

  // Summary counts
  const summaryCounts = useMemo(() => {
    let done = 0, running = 0, partial = 0, failed = 0;
    for (const { languages } of rows) {
      for (const lang of visibleLangs) {
        const s = cellStatus(languages[lang]);
        if (s === 'completed') done++;
        else if (s === 'running') running++;
        else if (s === 'pending') partial++;
        else if (s === 'failed') failed++;
      }
    }
    return { done, running, partial, failed };
  }, [rows, visibleLangs]);

  // M6b-2: chapters with a glossary-stale active translation in a visible language.
  const stale = useMemo(
    () => coverage ? staleChapterIds(coverage, visibleLangs) : { ids: new Set<string>(), cells: 0 },
    [coverage, visibleLangs],
  );
  // Only select stale chapters that are still active (a stale orphan can't be re-translated).
  const selectStale = () => setSelectedChapters(new Set([...stale.ids].filter((id) => chapterSet.has(id))));

  const manageVersions = (chapterId: string, lang: string) => {
    if (onManageVersions) { onManageVersions(chapterId, lang); return; }
    navigate(`/books/${bookId}/chapters/${chapterId}/translations?lang=${lang}`);
  };

  const isFiltered = selectedLangs !== null;
  const hiddenCount = allLanguages.length - visibleLangs.length;
  const allSelected = selectedChapters.size === allChapterIds.length && allChapterIds.length > 0;
  const hasChapters = chapters.length > 0;
  // D1: the header CTA opens the modal UNSCOPED (the modal owns scope, because scope depends on
  // the language the user has not chosen yet). Selection-scoped opens come from the floating bar.
  const openTranslateUnscoped = () => { setTranslateScoped(false); setTranslateOpen(true); };
  const openTranslateScoped = () => { setTranslateScoped(true); setTranslateOpen(true); };

  return (
    <div className="space-y-4 p-6">
      {/* Header — always rendered (D1): the Translate CTA must outlive the loading/error/empty
          branches, which now live inside the matrix region below. */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">{t('matrix.title')}</h3>
          <p className="text-xs text-muted-foreground">
            {t('matrix.chapters_count', { count: chapters.length })}
            {allLanguages.length > 0 && ` · ${t('matrix.target_langs', { count: visibleLangs.length })}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {allLanguages.length > 3 && (
            <button
              onClick={() => setFilterOpen(!filterOpen)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
                isFiltered ? 'border-primary/40 text-primary hover:bg-primary/10' : 'border-border text-muted-foreground hover:bg-secondary hover:text-foreground',
              )}
            >
              <Filter className="h-3.5 w-3.5" />
              {isFiltered ? t('matrix.selected_count', { count: visibleLangs.length }) : t('matrix.filter')}
            </button>
          )}
          <button
            onClick={openTranslateUnscoped}
            disabled={!hasChapters || !canEdit}
            data-testid="matrix-translate-cta"
            title={!canEdit ? t('matrix.translate_no_edit', { defaultValue: 'You have view-only access — ask the owner for edit access to translate.' }) : undefined}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Languages className="h-3.5 w-3.5" />
            {t('matrix.translate_cta', { defaultValue: 'Translate…' })}
          </button>
        </div>
      </div>

      {/* T9/D10-C: a visible reason, not just a disabled button — a view-only collaborator sees
          WHY they can't translate instead of a button that silently 403s at submit. */}
      {book?.access_level && !canEdit && (
        <div data-testid="matrix-view-only" className="rounded-md border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-[11px] text-amber-500">
          {t('matrix.translate_no_edit', { defaultValue: 'You have view-only access — ask the owner for edit access to translate.' })}
        </div>
      )}

      <TranslateModal
        open={translateOpen}
        onClose={() => setTranslateOpen(false)}
        bookId={bookId}
        onJobCreated={() => { invalidate(); clearSelection(); }}
        // T8/D6: a selection-scoped open inherits the ticked chapters and, when exactly one
        // language column is visible, that language; an unscoped open lets the modal derive scope.
        preselectedChapterIds={translateScoped ? [...selectedChapters] : undefined}
        preselectedLang={translateScoped && visibleLangs.length === 1 ? visibleLangs[0] : undefined}
      />

      {/* Language filter */}
      {filterOpen && (
        <div className="rounded-lg border bg-card p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">{t('matrix.show_languages')}</span>
            {isFiltered && (
              <button onClick={resetFilter} className="text-[10px] text-primary hover:underline">{t('matrix.reset_auto')}</button>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {allLanguages.map((lang) => {
              const active = visibleLangs.includes(lang);
              const hasData = autoLangs.has(lang);
              return (
                <button
                  key={lang}
                  onClick={() => toggleLang(lang)}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors',
                    active ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:border-border-hover hover:text-foreground',
                  )}
                >
                  {lang.toUpperCase()}
                  <span className="text-[9px] font-normal opacity-60">{getLanguageName(lang)}</span>
                  {hasData && !active && <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-green-500/60" />}
                  {active && <X className="h-3 w-3 ml-0.5 opacity-50" />}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-3" data-testid="matrix-loading">
          {/* T4: the skeleton must carry text — a textless skeleton reads as a broken panel. */}
          <p className="text-xs text-muted-foreground">{t('matrix.loading')}</p>
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : queryError ? (
        <TranslationErrorState error={queryError} onRetry={retryAll} />
      ) : !hasChapters ? (
        <EmptyState icon={Languages} title={t('matrix.no_chapters_title')} description={t('matrix.no_chapters_desc')} />
      ) : visibleLangs.length === 0 ? (
        isFiltered && allLanguages.length > 0 ? (
          // The book HAS translations — the user just filtered them all out. Don't claim "no
          // translations yet"; offer to reset the filter.
          <EmptyState
            icon={Filter}
            title={t('matrix.all_filtered_title', { defaultValue: 'All languages are filtered out' })}
            description={t('matrix.all_filtered_desc', { defaultValue: 'Re-enable a language in the filter to see its coverage.' })}
            action={
              <button
                onClick={resetFilter}
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110"
              >
                <Filter className="h-3.5 w-3.5" />
                {t('matrix.reset_auto')}
              </button>
            }
          />
        ) : (
          <EmptyState
            icon={Languages}
            title={t('matrix.no_translations_title')}
            description={t('matrix.no_translations_desc')}
            action={
              <button
                onClick={openTranslateUnscoped}
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110"
              >
                <Languages className="h-3.5 w-3.5" />
                {t('matrix.start_translation')}
              </button>
            }
          />
        )
      ) : (
        <>
          {/* Matrix table — one row per CHAPTER (D3), paged (D4). */}
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b" style={{ background: 'rgba(40,35,32,0.5)' }}>
                  <th className="w-9 px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAllChapters}
                      aria-label={t('matrix.select_all_chapters', { defaultValue: 'Select all chapters' })}
                      className="h-[15px] w-[15px] rounded accent-primary cursor-pointer"
                    />
                  </th>
                  <th className="px-3 py-2.5 text-left font-medium text-muted-foreground font-mono" style={{ width: 40 }}>#</th>
                  <th className="sticky left-0 z-10 px-3 py-2.5 text-left font-medium text-muted-foreground" style={{ minWidth: 180, background: 'rgba(40,35,32,0.5)' }}>
                    {t('matrix.col_chapter')}
                  </th>
                  {visibleLangs.map((lang) => (
                    <th key={lang} className="px-4 py-2.5 text-center font-medium text-muted-foreground" style={{ minWidth: 90 }}>
                      <div className="text-[11px] leading-tight">{getLanguageName(lang)}</div>
                      <div className="font-mono text-[9px] opacity-60">({lang})</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.map(({ ch, languages }, idx) => {
                  const isSelected = selectedChapters.has(ch.chapter_id);
                  const rowTitle = ch.title || ch.original_filename || ch.chapter_id.slice(0, 8);
                  return (
                    <tr
                      key={ch.chapter_id}
                      className={cn(
                        'border-b last:border-b-0 transition-colors',
                        isSelected ? 'bg-primary/[0.04]' : 'hover:bg-[rgba(255,255,255,0.01)]',
                      )}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleChapter(ch.chapter_id)}
                          aria-label={rowTitle}
                          className="h-[15px] w-[15px] rounded accent-primary cursor-pointer"
                        />
                      </td>
                      <td className="px-3 py-2 font-mono text-muted-foreground">{start + idx + 1}</td>
                      <td className="sticky left-0 z-10 bg-background px-3 py-2 font-medium">
                        <span className="line-clamp-1">{rowTitle}</span>
                      </td>
                      {visibleLangs.map((lang) => {
                        const cell = languages[lang];
                        const isStale = !!cell?.is_glossary_stale;
                        const hasVersions = !!cell && cell.version_count > 0;
                        // T2-M3: segments needing re-translation (source-dirty ∪ glossary-stale).
                        const needs = needsMap?.[ch.chapter_id]?.[lang] ?? 0;
                        const inner = (
                          <span className="inline-flex items-center justify-center gap-1">
                            {cellContent(cell, t)}
                            {isStale && (
                              <History className="h-2.5 w-2.5 shrink-0 text-sky-400" aria-label={t('matrix.cell_stale_title')} />
                            )}
                          </span>
                        );
                        const title = isStale
                          ? t('matrix.cell_stale_title')
                          : hasVersions
                            ? t('matrix.cell_manage_versions', { num: cell!.latest_version_num, count: cell!.version_count })
                            : t('matrix.cell_not_translated');
                        return (
                          <td
                            key={lang}
                            className={cn('px-4 py-2 text-center transition-colors', cellBg(cell))}
                            title={title}
                          >
                            {hasVersions ? (
                              <span className="inline-flex items-center justify-center gap-1.5">
                                {/* Click a translated cell to manage its versions / publish a
                                    version active (the version page was previously unreachable). */}
                                <button
                                  type="button"
                                  onClick={() => manageVersions(ch.chapter_id, lang)}
                                  aria-label={t('matrix.cell_manage_versions', { num: cell!.latest_version_num, count: cell!.version_count })}
                                  className="inline-flex items-center justify-center gap-1 rounded px-1.5 py-0.5 cursor-pointer hover:bg-primary/10 hover:underline focus:outline-none focus:ring-1 focus:ring-ring/40"
                                >
                                  {inner}
                                </button>
                                {/* T2-M3: "N changed" badge → per-segment drill-down + re-translate. */}
                                {needs > 0 && (
                                  <button
                                    type="button"
                                    onClick={() => setDrillTarget({ chapterId: ch.chapter_id, lang, title: ch.title || ch.original_filename })}
                                    title={t('matrix.cell_changed_title', { count: needs })}
                                    aria-label={t('matrix.cell_changed_title', { count: needs })}
                                    className="inline-flex items-center gap-0.5 rounded-full border border-amber-500/40 px-1.5 py-0.5 text-[10px] font-medium text-amber-500 hover:bg-amber-500/10 focus:outline-none focus:ring-1 focus:ring-ring/40"
                                  >
                                    <RefreshCw className="h-2.5 w-2.5" />
                                    {needs}
                                  </button>
                                )}
                              </span>
                            ) : (
                              <span className="cursor-default">{inner}</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* D5: orphan coverage — translations belonging to a chapter that is no longer active
              are surfaced, never silently dropped by the one-row-per-chapter left-join. */}
          {orphanCount > 0 && (
            <p className="text-[10px] text-muted-foreground" data-testid="matrix-orphan-footnote">
              {t('matrix.orphan_footnote', {
                count: orphanCount,
                defaultValue: '{{count}} translation(s) belong to chapters that are no longer active.',
              })}
            </p>
          )}

          {/* D4: pagination — selection is by id and survives a page change. */}
          <Pager
            page={page}
            pageCount={pageCount}
            onPageChange={setPage}
            className="justify-center"
            labels={{ page: t('matrix.page', { defaultValue: 'Page' }), prev: t('matrix.prev', { defaultValue: 'Prev' }), next: t('matrix.next', { defaultValue: 'Next' }) }}
          />

          {/* Summary legend */}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{t('matrix.showing_chapters', { shown: pageRows.length, total: chapters.length })}</span>
            <div className="flex items-center gap-3">
              {stale.cells > 0 && (
                <button
                  onClick={selectStale}
                  title={t('matrix.select_affected_title')}
                  className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/40 px-2 py-0.5 text-sky-400 hover:bg-sky-400/10 transition-colors"
                >
                  <History className="h-3 w-3" />
                  {t('matrix.legend_stale', { count: stale.ids.size })}
                </button>
              )}
              {summaryCounts.done > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-green-500" />{t('matrix.legend_translated', { count: summaryCounts.done })}
                </span>
              )}
              {summaryCounts.running > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-400" />{t('matrix.legend_running', { count: summaryCounts.running })}
                </span>
              )}
              {summaryCounts.partial > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-amber-400" />{t('matrix.legend_pending', { count: summaryCounts.partial })}
                </span>
              )}
              {summaryCounts.failed > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-destructive" />{t('matrix.legend_failed', { count: summaryCounts.failed })}
                </span>
              )}
            </div>
          </div>

          {hiddenCount > 0 && !filterOpen && (
            <p className="text-[10px] text-muted-foreground text-center">
              {t('matrix.more_hidden', { count: hiddenCount })}{' '}
              <button onClick={() => setFilterOpen(true)} className="text-primary hover:underline">{t('matrix.show_filter')}</button>
            </p>
          )}
        </>
      )}

      {/* Floating action bar when chapters selected */}
      <FloatingActionBar visible={selectedChapters.size > 0}>
        <span className="text-sm font-medium">{t('matrix.chapters_selected', { count: selectedChapters.size })}</span>
        <FloatingActionDivider />
        <button
          onClick={openTranslateScoped}
          disabled={!canEdit}
          title={!canEdit ? t('matrix.translate_no_edit', { defaultValue: 'You have view-only access — ask the owner for edit access to translate.' }) : undefined}
          data-testid="matrix-translate-selected"
          className="btn-glow inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Languages className="h-3.5 w-3.5" />
          {t('matrix.translate_selected')}
        </button>
        <button
          onClick={() => setExtractionOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/5 px-4 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
        >
          <Sparkles className="h-3.5 w-3.5" />
          {t('matrix.extract_glossary')}
        </button>
        <button onClick={clearSelection} className="text-xs text-muted-foreground hover:text-foreground transition-colors">
          {t('matrix.clear')}
        </button>
      </FloatingActionBar>

      <ExtractionWizard
        open={extractionOpen}
        onOpenChange={setExtractionOpen}
        bookId={bookId}
        mode={selectedChapters.size <= 1 ? 'single' : 'batch'}
        preselectedChapterIds={[...selectedChapters]}
      />

      {/* T2-M3: per-segment drill-down + dirty-only re-translate. */}
      <SegmentDrilldownModal
        bookId={bookId}
        target={drillTarget}
        onClose={() => { setDrillTarget(null); invalidate(); }}
      />
    </div>
  );
}
