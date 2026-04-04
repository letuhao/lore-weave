import { useState, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Languages, Check, Clock, AlertCircle, Loader2, Plus, Filter, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { translationApi, type BookCoverageResponse, type CoverageCell } from '@/features/translation/api';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState, FloatingActionBar, FloatingActionDivider } from '@/components/shared';
import { cn } from '@/lib/utils';
import { getLanguageName } from '@/lib/languages';
import { TranslateModal } from './TranslateModal';

function cellContent(cell: CoverageCell | undefined) {
  if (!cell || cell.version_count === 0) {
    return <span className="text-[11px] text-muted-foreground">—</span>;
  }
  const s = cell.latest_status;
  if (s === 'completed' && cell.has_active) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-green-500">
        <Check className="h-3 w-3" strokeWidth={2.5} />
        Done
      </span>
    );
  }
  if (s === 'completed') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-green-500/60">
        <Check className="h-3 w-3" strokeWidth={2.5} />
        Done
      </span>
    );
  }
  if (s === 'running') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-blue-400">
        <Loader2 className="h-3 w-3 animate-spin" />
        Running
      </span>
    );
  }
  if (s === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-destructive">
        <X className="h-3 w-3" strokeWidth={2.5} />
        Failed
      </span>
    );
  }
  if (s === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-amber-400">
        <Clock className="h-3 w-3" />
        Pending
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

export function TranslationTab({ bookId }: { bookId: string }) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [selectedLangs, setSelectedLangs] = useState<Set<string> | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);
  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set());

  const { data: coverageData, isLoading: coverageLoading, error: coverageError } = useQuery({
    queryKey: ['translation-coverage', bookId],
    queryFn: () => translationApi.getBookCoverage(accessToken!, bookId),
    enabled: !!accessToken,
  });

  const { data: chaptersData } = useQuery({
    queryKey: ['chapters', bookId, 'all'],
    queryFn: () => booksApi.listChapters(accessToken!, bookId, { lifecycle_state: 'active', limit: 200, offset: 0 }),
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
      <EmptyState icon={Languages} title="No chapters to translate" description="Create chapters first, then come back to translate them." />
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
          <h3 className="text-sm font-semibold">Translation Matrix</h3>
          <p className="text-xs text-muted-foreground">
            {chapters.length} chapter{chapters.length !== 1 ? 's' : ''}
            {allLanguages.length > 0 && ` · ${visibleLangs.length} target language${visibleLangs.length !== 1 ? 's' : ''}`}
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
              {isFiltered ? `${visibleLangs.length} selected` : 'Filter'}
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
            <span className="text-xs font-medium text-muted-foreground">Show languages</span>
            {isFiltered && (
              <button onClick={resetFilter} className="text-[10px] text-primary hover:underline">Reset to auto</button>
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
        <EmptyState icon={Languages} title="No translations yet" description="Select chapters and click 'Translate Selected' to start." />
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
                    Chapter
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
                        return (
                          <td
                            key={lang}
                            className={cn('px-4 py-2 text-center cursor-default transition-colors', cellBg(cell))}
                            title={cell && cell.version_count > 0 ? `v${cell.latest_version_num} · ${cell.version_count} version(s)` : 'Not translated'}
                          >
                            {cellContent(cell)}
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
            <span>Showing {coverage.coverage.length} of {chapters.length} chapters</span>
            <div className="flex items-center gap-3">
              {summaryCounts.done > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-green-500" />{summaryCounts.done} translated
                </span>
              )}
              {summaryCounts.running > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-400" />{summaryCounts.running} running
                </span>
              )}
              {summaryCounts.partial > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-amber-400" />{summaryCounts.partial} pending
                </span>
              )}
              {summaryCounts.failed > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-destructive" />{summaryCounts.failed} failed
                </span>
              )}
            </div>
          </div>

          {hiddenCount > 0 && !filterOpen && (
            <p className="text-[10px] text-muted-foreground text-center">
              {hiddenCount} more language{hiddenCount !== 1 ? 's' : ''} hidden ·{' '}
              <button onClick={() => setFilterOpen(true)} className="text-primary hover:underline">show filter</button>
            </p>
          )}
        </>
      )}

      {/* Floating action bar when chapters selected */}
      <FloatingActionBar visible={selectedChapters.size > 0}>
        <span className="text-sm font-medium">{selectedChapters.size} chapter{selectedChapters.size !== 1 ? 's' : ''} selected</span>
        <FloatingActionDivider />
        <button
          onClick={() => setTranslateOpen(true)}
          className="btn-glow inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground"
        >
          <Languages className="h-3.5 w-3.5" />
          Translate Selected
        </button>
        <button onClick={clearSelection} className="text-xs text-muted-foreground hover:text-foreground transition-colors">
          Clear
        </button>
      </FloatingActionBar>
    </div>
  );
}
