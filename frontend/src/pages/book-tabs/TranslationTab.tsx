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
import { TranslateModal } from './TranslateModal';
import { SegmentDrilldownModal } from '@/features/translation/components/SegmentDrilldownModal';
import { ExtractionWizard } from '@/features/extraction/ExtractionWizard';

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

export function TranslationTab({ bookId }: { bookId: string }) {
  const { t } = useTranslation('translation');
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedLangs, setSelectedLangs] = useState<Set<string> | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);
  const [extractionOpen, setExtractionOpen] = useState(false);
  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set());
  // T2-M3: per-segment drill-down target (chapter × language), null when closed.
  const [drillTarget, setDrillTarget] = useState<{ chapterId: string; lang: string; title?: string } | null>(null);

  const { data: coverageData, isLoading: coverageLoading, error: coverageError } = useQuery({
    queryKey: ['translation-coverage', bookId],
    queryFn: () => translationApi.getBookCoverage(accessToken!, bookId),
    enabled: !!accessToken,
  });

  // C: loop-fetch ALL active chapters (the backend clamps a single request to 100, so
  // a >100-chapter book would otherwise lose titles past the first page).
  const { data: chaptersData } = useQuery({
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

  const coverage = coverageData ?? null;
  const chapters = chaptersData?.items ?? [];
  const loading = coverageLoading;
  const error = coverageError ? (coverageError as Error).message : '';

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['translation-coverage', bookId] });

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

  // Chapter selection
  const toggleChapter = (id: string) => {
    setSelectedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleAllChapters = () => {
    if (!coverage) return;
    const allIds = coverage.coverage.map((r) => r.chapter_id);
    setSelectedChapters((prev) => prev.size === allIds.length ? new Set() : new Set(allIds));
  };
  const clearSelection = () => setSelectedChapters(new Set());

  // Summary counts
  const summaryCounts = useMemo(() => {
    if (!coverage) return { done: 0, running: 0, partial: 0, failed: 0 };
    let done = 0, running = 0, partial = 0, failed = 0;
    for (const row of coverage.coverage) {
      for (const lang of visibleLangs) {
        const s = cellStatus(row.languages[lang]);
        if (s === 'completed') done++;
        else if (s === 'running') running++;
        else if (s === 'pending') partial++;
        else if (s === 'failed') failed++;
      }
    }
    return { done, running, partial, failed };
  }, [coverage, visibleLangs]);

  // M6b-2: chapters with a glossary-stale active translation in a visible language.
  const stale = useMemo(
    () => coverage ? staleChapterIds(coverage, visibleLangs) : { ids: new Set<string>(), cells: 0 },
    [coverage, visibleLangs],
  );
  const selectStale = () => setSelectedChapters(new Set(stale.ids));

  if (loading) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) return <div className="p-6 text-sm text-destructive">{error}</div>;

  if (!coverage || chapters.length === 0) {
    return (
      <EmptyState icon={Languages} title={t('matrix.no_chapters_title')} description={t('matrix.no_chapters_desc')} />
    );
  }

  const chapterMap = new Map(chapters.map((c) => [c.chapter_id, c]));
  const isFiltered = selectedLangs !== null;
  const hiddenCount = allLanguages.length - visibleLangs.length;
  const allSelected = selectedChapters.size === coverage.coverage.length && coverage.coverage.length > 0;

  return (
    <div className="space-y-4 p-6">
      {/* Header */}
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
        </div>
      </div>

      <TranslateModal
        open={translateOpen}
        onClose={() => setTranslateOpen(false)}
        bookId={bookId}
        onJobCreated={() => { invalidate(); clearSelection(); }}
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

      {visibleLangs.length === 0 ? (
        <EmptyState
          icon={Languages}
          title={t('matrix.no_translations_title')}
          description={t('matrix.no_translations_desc')}
          action={
            <button
              onClick={() => setTranslateOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:brightness-110"
            >
              <Languages className="h-3.5 w-3.5" />
              {t('matrix.start_translation')}
            </button>
          }
        />
      ) : (
        <>
          {/* Matrix table */}
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b" style={{ background: 'rgba(40,35,32,0.5)' }}>
                  <th className="w-9 px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAllChapters}
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
                {coverage.coverage.map((row, idx) => {
                  const ch = chapterMap.get(row.chapter_id);
                  const isSelected = selectedChapters.has(row.chapter_id);
                  return (
                    <tr
                      key={row.chapter_id}
                      className={cn(
                        'border-b last:border-b-0 transition-colors',
                        isSelected ? 'bg-primary/[0.04]' : 'hover:bg-[rgba(255,255,255,0.01)]',
                      )}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleChapter(row.chapter_id)}
                          className="h-[15px] w-[15px] rounded accent-primary cursor-pointer"
                        />
                      </td>
                      <td className="px-3 py-2 font-mono text-muted-foreground">{idx + 1}</td>
                      <td className="sticky left-0 z-10 bg-background px-3 py-2 font-medium">
                        <span className="line-clamp-1">{ch?.title || ch?.original_filename || row.chapter_id.slice(0, 8)}</span>
                      </td>
                      {visibleLangs.map((lang) => {
                        const cell = row.languages[lang];
                        const isStale = !!cell?.is_glossary_stale;
                        const hasVersions = !!cell && cell.version_count > 0;
                        // T2-M3: segments needing re-translation (source-dirty ∪ glossary-stale).
                        const needs = needsMap?.[row.chapter_id]?.[lang] ?? 0;
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
                                  onClick={() => navigate(`/books/${bookId}/chapters/${row.chapter_id}/translations?lang=${lang}`)}
                                  aria-label={t('matrix.cell_manage_versions', { num: cell!.latest_version_num, count: cell!.version_count })}
                                  className="inline-flex items-center justify-center gap-1 rounded px-1.5 py-0.5 cursor-pointer hover:bg-primary/10 hover:underline focus:outline-none focus:ring-1 focus:ring-ring/40"
                                >
                                  {inner}
                                </button>
                                {/* T2-M3: "N changed" badge → per-segment drill-down + re-translate. */}
                                {needs > 0 && (
                                  <button
                                    type="button"
                                    onClick={() => setDrillTarget({ chapterId: row.chapter_id, lang, title: ch?.title || ch?.original_filename })}
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

          {/* Summary legend */}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>{t('matrix.showing_chapters', { shown: coverage.coverage.length, total: chapters.length })}</span>
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
          onClick={() => setTranslateOpen(true)}
          className="btn-glow inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground"
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
