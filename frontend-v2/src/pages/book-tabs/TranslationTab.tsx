import { useEffect, useState, useMemo } from 'react';
import { Languages, Check, Clock, AlertCircle, Loader2, Plus, Filter, X } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { translationApi, type BookCoverageResponse, type CoverageCell } from '@/features/translation/api';
import { Skeleton } from '@/components/shared/Skeleton';
import { EmptyState } from '@/components/shared';
import { cn } from '@/lib/utils';
import { getLanguageName } from '@/lib/languages';

function statusIcon(cell: CoverageCell | undefined) {
  if (!cell || cell.version_count === 0) return null;
  const s = cell.latest_status;
  if (s === 'completed' && cell.has_active) return <Check className="h-3.5 w-3.5 text-green-500" />;
  if (s === 'completed') return <Check className="h-3.5 w-3.5 text-green-500/50" />;
  if (s === 'running') return <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin" />;
  if (s === 'failed') return <AlertCircle className="h-3.5 w-3.5 text-destructive" />;
  if (s === 'pending') return <Clock className="h-3.5 w-3.5 text-amber-400" />;
  return null;
}

function cellClass(cell: CoverageCell | undefined): string {
  if (!cell || cell.version_count === 0) return '';
  const s = cell.latest_status;
  if (s === 'completed' && cell.has_active) return 'bg-green-500/8';
  if (s === 'completed') return 'bg-green-500/4';
  if (s === 'running') return 'bg-blue-400/6';
  if (s === 'failed') return 'bg-destructive/6';
  if (s === 'pending') return 'bg-amber-400/6';
  return '';
}

function cellTooltip(cell: CoverageCell | undefined): string {
  if (!cell || cell.version_count === 0) return 'Not translated';
  const parts: string[] = [];
  if (cell.latest_status) parts.push(cell.latest_status);
  if (cell.version_count > 0) parts.push(`v${cell.latest_version_num ?? '?'}`);
  if (cell.version_count > 1) parts.push(`(${cell.version_count} versions)`);
  if (cell.has_active) parts.push('· active');
  return parts.join(' ');
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
  const [coverage, setCoverage] = useState<BookCoverageResponse | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedLangs, setSelectedLangs] = useState<Set<string> | null>(null); // null = auto
  const [filterOpen, setFilterOpen] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    Promise.all([
      translationApi.getBookCoverage(accessToken, bookId),
      booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 200, offset: 0 }),
    ])
      .then(([cov, chs]) => {
        setCoverage(cov);
        setChapters(chs.items);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [accessToken, bookId]);

  // Compute visible languages: user-selected or auto (languages with data)
  const allLanguages = coverage?.known_languages ?? [];
  const autoLangs = useMemo(
    () => coverage ? languagesWithData(coverage) : new Set<string>(),
    [coverage],
  );
  const visibleLangs = useMemo(() => {
    if (selectedLangs) return allLanguages.filter((l) => selectedLangs.has(l));
    // Auto: show languages with data, or all if none have data
    const withData = allLanguages.filter((l) => autoLangs.has(l));
    return withData.length > 0 ? withData : allLanguages;
  }, [allLanguages, selectedLangs, autoLangs]);

  const toggleLang = (lang: string) => {
    setSelectedLangs((prev) => {
      const next = new Set(prev ?? autoLangs);
      if (next.has(lang)) next.delete(lang);
      else next.add(lang);
      return next;
    });
  };

  const resetFilter = () => {
    setSelectedLangs(null);
    setFilterOpen(false);
  };

  if (loading) {
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

  if (!coverage || chapters.length === 0) {
    return (
      <EmptyState
        icon={Languages}
        title="No chapters to translate"
        description="Create chapters first, then come back to translate them."
      />
    );
  }

  const chapterMap = new Map(chapters.map((c) => [c.chapter_id, c]));
  const isFiltered = selectedLangs !== null;
  const hiddenCount = allLanguages.length - visibleLangs.length;

  return (
    <div className="space-y-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Translation Coverage</h3>
          <p className="text-xs text-muted-foreground">
            {chapters.length} chapter{chapters.length !== 1 ? 's' : ''}
            {allLanguages.length > 0 && ` · ${visibleLangs.length} of ${allLanguages.length} language${allLanguages.length !== 1 ? 's' : ''}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {allLanguages.length > 3 && (
            <button
              onClick={() => setFilterOpen(!filterOpen)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
                isFiltered
                  ? 'border-primary/40 text-primary hover:bg-primary/10'
                  : 'border-border text-muted-foreground hover:bg-secondary hover:text-foreground',
              )}
            >
              <Filter className="h-3.5 w-3.5" />
              {isFiltered ? `${visibleLangs.length} selected` : 'Filter'}
            </button>
          )}
          <button className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90">
            <Plus className="h-3.5 w-3.5" />
            Translate
          </button>
        </div>
      </div>

      {/* Language filter dropdown */}
      {filterOpen && (
        <div className="rounded-lg border bg-card p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Show languages</span>
            {isFiltered && (
              <button onClick={resetFilter} className="text-[10px] text-primary hover:underline">
                Reset to auto
              </button>
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
                    active
                      ? 'border-primary/40 bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:border-border-hover hover:text-foreground',
                  )}
                >
                  {lang.toUpperCase()}
                  <span className="text-[9px] font-normal opacity-60">
                    {getLanguageName(lang)}
                  </span>
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
          title="No translations yet"
          description="Click 'Translate' to start translating your chapters."
        />
      ) : (
        <>
          {/* Matrix table */}
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-card">
                  <th className="sticky left-0 z-10 bg-card px-4 py-2.5 text-left font-medium text-muted-foreground" style={{ minWidth: 200 }}>
                    Chapter
                  </th>
                  {visibleLangs.map((lang) => (
                    <th key={lang} className="px-3 py-2.5 text-center font-medium text-muted-foreground" style={{ minWidth: 80 }}>
                      <span title={getLanguageName(lang)}>{lang.toUpperCase()}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {coverage.coverage.map((row) => {
                  const ch = chapterMap.get(row.chapter_id);
                  return (
                    <tr key={row.chapter_id} className="border-b last:border-b-0 hover:bg-card/50 transition-colors">
                      <td className="sticky left-0 z-10 bg-background px-4 py-2.5 font-medium">
                        <span className="line-clamp-1">{ch?.title || ch?.original_filename || row.chapter_id.slice(0, 8)}</span>
                      </td>
                      {visibleLangs.map((lang) => {
                        const cell = row.languages[lang];
                        return (
                          <td
                            key={lang}
                            className={cn('px-3 py-2.5 text-center cursor-default transition-colors', cellClass(cell))}
                            title={cellTooltip(cell)}
                          >
                            <div className="flex items-center justify-center gap-1">
                              {statusIcon(cell)}
                              {cell && cell.version_count > 0 && (
                                <span className="text-[10px] text-muted-foreground">
                                  v{cell.latest_version_num}
                                </span>
                              )}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {hiddenCount > 0 && !filterOpen && (
            <p className="text-[10px] text-muted-foreground text-center">
              {hiddenCount} more language{hiddenCount !== 1 ? 's' : ''} hidden ·{' '}
              <button onClick={() => setFilterOpen(true)} className="text-primary hover:underline">show filter</button>
            </p>
          )}
        </>
      )}
    </div>
  );
}
