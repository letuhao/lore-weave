import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  useRawSearch,
  type RawSearchMode,
  type RawSearchGranularity,
  type RawSearchSurface,
} from '../hooks/useRawSearch';
import { useIndexDrafts } from '../hooks/useIndexDrafts';
import { useDebouncedValue } from '../hooks/useDebouncedValue';
import { RawSearchResultCard } from './RawSearchResultCard';

// "View" surface for raw search (MVC: logic in useRawSearch, render here).

export interface RawSearchPanelProps {
  bookId: string;
  // S-11 — the studio hosts this panel and wants a hit to open the in-dock editor at the
  // chapter (host.focusManuscriptUnit), NOT navigate away to the reader route. Optional so the
  // standalone RawSearchPage + ChapterBrowser keep the default reader-navigation behaviour.
  onJump?: (chapterId: string, blockIndex?: number) => void;
  // S-11 — seed the query box (the studio search rail passes the query the user typed). Optional;
  // uncontrolled thereafter (the box owns edits). Remount (key=query) to re-seed a new rail query.
  initialQuery?: string;
}

const MODES: RawSearchMode[] = ['hybrid', 'lexical'];
const GRANULARITIES: RawSearchGranularity[] = ['chapter', 'block'];
const SURFACES: RawSearchSurface[] = ['canon', 'all'];
const LIMITS = [10, 20, 50, 100] as const;

export function RawSearchPanel({ bookId, onJump: onJumpProp, initialQuery }: RawSearchPanelProps) {
  const { t } = useTranslation('rawSearch');
  const navigate = useNavigate();
  const [input, setInput] = useState(initialQuery ?? '');
  const [mode, setMode] = useState<RawSearchMode>('hybrid');
  // E6 — Navigate (chapter, best-per-chapter) vs Mine (block, every match).
  const [granularity, setGranularity] = useState<RawSearchGranularity>('chapter');
  // D-RAWSEARCH-CANON-WIRING — canon (published only) vs all (incl. owner's drafts).
  const [surface, setSurface] = useState<RawSearchSurface>('canon');
  const [limit, setLimit] = useState<number>(20);
  // Debounce so a real BE query doesn't fire on every keystroke (review-impl MED-2).
  const debouncedQuery = useDebouncedValue(input, 250);
  // Owner-only draft search + on-demand indexing (the BE enforces it too).
  const { isOwner, indexDrafts, isIndexing, result: indexResult, error: indexError } =
    useIndexDrafts(bookId);
  // A non-owner can never use surface=all (BE downgrades it) → keep it at canon.
  const effectiveSurface: RawSearchSurface = isOwner ? surface : 'canon';
  const { hits, disabled, isFetching, error, degraded } = useRawSearch(
    bookId, debouncedQuery, { mode, granularity, limit, surface: effectiveSurface },
  );

  // Jump-to-source: open the chapter reader and scroll to the matched block.
  // Lexical hits carry a blockIndex (→ ?block=N, the reader scrolls there).
  // Semantic hits have only a chunkIndex (not a block index) → open the chapter
  // without precise scroll (full semantic precision deferred).
  const onJump = (chapterId: string, blockIndex?: number) => {
    // S-11 — a studio host injects onJump to open the in-dock editor at the chapter; without it
    // (standalone page / chapter-browser) we keep the reader-route navigation.
    if (onJumpProp) {
      onJumpProp(chapterId, blockIndex);
      return;
    }
    const target = blockIndex != null ? `?block=${blockIndex}` : '';
    navigate(`/books/${bookId}/chapters/${chapterId}/read${target}`);
  };
  const isDegraded = Object.keys(degraded).length > 0;

  return (
    <div className="flex flex-col gap-3" data-testid="raw-search-panel">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('placeholder')}
            aria-label={t('placeholder')}
            data-testid="raw-search-input"
            className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
        <div
          className="flex rounded-md border p-0.5"
          role="group"
          aria-label={t('mode_label')}
        >
          {MODES.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              data-testid={`raw-search-mode-${m}`}
              className={cn(
                'rounded px-2 py-1 text-xs font-medium transition-colors',
                mode === m
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(`mode_${m}`)}
            </button>
          ))}
        </div>
      </div>

      {/* E6 options row — granularity (Navigate/Mine) + result count (K). */}
      <div className="flex items-center justify-between gap-2">
        <div
          className="flex rounded-md border p-0.5"
          role="group"
          aria-label={t('granularity_label')}
        >
          {GRANULARITIES.map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGranularity(g)}
              aria-pressed={granularity === g}
              title={t(`granularity_${g}_hint`)}
              data-testid={`raw-search-granularity-${g}`}
              className={cn(
                'rounded px-2 py-1 text-xs font-medium transition-colors',
                granularity === g
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(`granularity_${g}`)}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {t('limit_label')}
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            data-testid="raw-search-limit"
            className="rounded-md border bg-background px-1.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring/40"
          >
            {LIMITS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
      </div>

      {/* D-RAWSEARCH-CANON-WIRING — owner-only: canon/all surface + on-demand
          draft indexing. Drafts are the owner's private workspace, so this row
          is hidden for collaborators (and the BE enforces the same). */}
      {isOwner && (
        <div className="flex items-center justify-between gap-2">
          <div
            className="flex rounded-md border p-0.5"
            role="group"
            aria-label={t('surface_label')}
          >
            {SURFACES.map((sf) => (
              <button
                key={sf}
                type="button"
                onClick={() => setSurface(sf)}
                aria-pressed={surface === sf}
                title={t(`surface_${sf}_hint`)}
                data-testid={`raw-search-surface-${sf}`}
                className={cn(
                  'rounded px-2 py-1 text-xs font-medium transition-colors',
                  surface === sf
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t(`surface_${sf}`)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {indexResult && !indexError && (
              <span
                className="text-xs text-muted-foreground"
                data-testid="raw-search-index-drafts-result"
              >
                {t('index_drafts_done', {
                  indexed: indexResult.indexed,
                  chapters: indexResult.chapters,
                })}
              </span>
            )}
            {indexError && (
              <span
                className="text-xs text-destructive"
                data-testid="raw-search-index-drafts-error"
              >
                {t('index_drafts_error')}
              </span>
            )}
            <button
              type="button"
              onClick={() => indexDrafts()}
              disabled={isIndexing}
              title={t('index_drafts_hint')}
              data-testid="raw-search-index-drafts"
              className="rounded-md border px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
            >
              {isIndexing ? t('index_drafts_busy') : t('index_drafts')}
            </button>
          </div>
        </div>
      )}

      {isDegraded && !error && (
        <p
          className="text-xs text-amber-600 dark:text-amber-400"
          data-testid="raw-search-degraded"
        >
          {t('degraded')}
        </p>
      )}
      {error && (
        <p className="text-sm text-destructive" role="alert" data-testid="raw-search-error">
          {t('error')}
        </p>
      )}
      {!error && disabled && (
        <p className="text-sm text-muted-foreground" data-testid="raw-search-hint">
          {t('hint')}
        </p>
      )}
      {!error && !disabled && isFetching && hits.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="raw-search-loading">
          {t('loading')}
        </p>
      )}
      {!error && !disabled && !isFetching && hits.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="raw-search-empty">
          {t('no_results')}
        </p>
      )}
      {hits.length > 0 && (
        <ul className="divide-y rounded-md border" data-testid="raw-search-results">
          {hits.map((hit) => (
            <RawSearchResultCard
              key={`${hit.chapterId}:${hit.matchType}:${hit.location.blockIndex ?? hit.location.chunkIndex}`}
              hit={hit}
              onJump={onJump}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
