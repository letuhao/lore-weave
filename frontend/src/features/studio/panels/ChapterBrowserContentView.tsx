// 15_chapter_browser.md B2 — Content (full-text) search mode for the `chapter-browser` dock
// panel. DOCK-2: this is NOT a fork of RawSearchPanel's fetch/search logic — it reuses
// useRawSearch / useIndexDrafts / useDebouncedValue / renderHighlight AS-IS and only restyles
// the result rendering to the denser "snippet-card" density from the approved design draft
// (design-drafts/screens/studio/screen-chapter-browser.html — "Content (full-text)" mode):
// chapter title + heading-context breadcrumb, a surface badge (draft/canon), a relevance meter,
// the matched snippet with the query term(s) highlighted via <mark>, and a footer with the
// block position + a "Jump to source" action.
//
// This component is a SUB-VIEW composed by ChapterBrowserPanel.tsx (another agent's file, same
// milestone) — it is not itself a dockview panel (no IDockviewPanelProps, no useStudioPanel/
// useRegisterStudioTool registration; the panel shell owns that per CB2). It only needs
// `bookId`, exactly like RawSearchPanel.
//
// DOCK-7 — "Jump to source" must NOT navigate/route (this is a studio panel, not a page).
// RawSearchPanel's `onJump` calls the standalone reader route's `navigate(...?block=N)`;
// BookReaderPanel (the studio's own `book-reader` dock panel) reads only `{bookId, chapterId}`
// from props.params today and has no block-scroll param equivalent — so, exactly like
// RawSearchPanel's own comment already documents for semantic hits (chunkIndex, no block
// index), we open the chapter WITHOUT a precise scroll target. This is an accepted v1
// limitation (spec 15_chapter_browser.md, out-of-scope note), not a silent gap: BookReaderPanel
// would need a params-driven scroll target (mirroring ReaderPage's `?block=N` handling) to
// close it, tracked for whoever builds that next, not invented here.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpRight, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  useRawSearch,
  type RawSearchMode,
  type RawSearchGranularity,
  type RawSearchSurface,
} from '@/features/raw-search/hooks/useRawSearch';
import { useIndexDrafts } from '@/features/raw-search/hooks/useIndexDrafts';
import { useDebouncedValue } from '@/features/raw-search/hooks/useDebouncedValue';
import { renderHighlight } from '@/features/raw-search/components/renderHighlight';
import type { RawSearchHit } from '@/features/raw-search/types';
import { useStudioHost } from '../host/StudioHostProvider';

export interface ChapterBrowserContentViewProps {
  bookId: string;
}

const MODES: RawSearchMode[] = ['hybrid', 'lexical'];
const GRANULARITIES: RawSearchGranularity[] = ['chapter', 'block'];
const SURFACES: RawSearchSurface[] = ['canon', 'all'];
const LIMITS = [10, 20, 50, 100] as const;

// Local display-only map (surface badge color) — mirrors RawSearchResultCard's SURFACE_CLASSES.
// Not exported from there, so a 2-entry style map here is a restyle, not a logic fork.
const SURFACE_BADGE_CLASSES: Record<string, string> = {
  draft: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  canon: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
};

const clamp01 = (n: number): number => Math.max(0, Math.min(1, n));

function chapterHeadingLabel(t: (k: string, o?: Record<string, unknown>) => string, hit: RawSearchHit): string {
  const chNum = t('content_view.chapter_label', { n: hit.sortOrder });
  return hit.chapterTitle ? `${chNum} — ${hit.chapterTitle}` : chNum;
}

// Snippet card — the restyled result row (design draft's `.snippet-card`). Private to this
// file: it renders ONE RawSearchHit at the Chapter Browser's density, not RawSearchResultCard's.
function ChapterBrowserSnippetCard({ hit, onJump }: { hit: RawSearchHit; onJump: (chapterId: string) => void }) {
  const { t } = useTranslation('rawSearch');
  const relevancePct = hit.relevance != null ? Math.round(clamp01(hit.relevance) * 100) : null;
  const filledTicks = relevancePct != null ? Math.max(1, Math.round(relevancePct / 20)) : 0;
  const positionLabel = hit.location.blockIndex != null
    ? t('content_view.block_position', { n: hit.location.blockIndex })
    : hit.location.chunkIndex != null
      ? t('content_view.passage_position', { n: hit.location.chunkIndex })
      : null;

  return (
    <li
      data-testid="chapter-browser-snippet-card"
      className="rounded-lg border bg-card p-3 transition-colors hover:border-foreground/20 hover:bg-muted/40"
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className="truncate text-[12.5px] font-semibold text-foreground" data-testid="chapter-browser-snippet-title">
          {chapterHeadingLabel(t, hit)}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide',
              SURFACE_BADGE_CLASSES[hit.surface] ?? 'bg-muted text-muted-foreground',
            )}
            data-testid="chapter-browser-snippet-surface"
          >
            {hit.surface}
          </span>
          {relevancePct != null && (
            <span
              className="flex items-center gap-0.5"
              role="meter"
              aria-label={`${t('relevance_label')} ${relevancePct}%`}
              aria-valuenow={relevancePct}
              aria-valuemin={0}
              aria-valuemax={100}
              title={`${relevancePct}%`}
              data-testid="chapter-browser-snippet-relevance"
            >
              {Array.from({ length: 5 }, (_, i) => (
                <span
                  key={i}
                  className={cn('h-2.5 w-[3px] rounded-sm', i < filledTicks ? 'bg-primary' : 'bg-muted')}
                />
              ))}
            </span>
          )}
        </span>
      </div>

      {hit.location.headingContext && (
        <p className="mb-1 truncate font-mono text-[10px] text-muted-foreground/70" data-testid="chapter-browser-snippet-crumb">
          § {hit.location.headingContext}
        </p>
      )}

      <p className="line-clamp-3 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-muted-foreground" data-testid="chapter-browser-snippet-body">
        {renderHighlight(hit.snippet, hit.highlights)}
      </p>

      <div className="mt-2 flex items-center justify-between">
        {positionLabel ? (
          <span className="font-mono text-[10px] text-muted-foreground/70" data-testid="chapter-browser-snippet-position">
            {positionLabel}
          </span>
        ) : <span />}
        <button
          type="button"
          onClick={() => onJump(hit.chapterId)}
          data-testid="chapter-browser-snippet-jump"
          className="flex items-center gap-1 text-[10.5px] font-medium text-accent-foreground hover:underline"
        >
          {t('content_view.jump')}
          <ArrowUpRight className="h-3 w-3" />
        </button>
      </div>
    </li>
  );
}

/** Content (full-text) search mode of the Chapter Browser panel (15_chapter_browser.md B2). */
export function ChapterBrowserContentView({ bookId }: ChapterBrowserContentViewProps) {
  const { t } = useTranslation('rawSearch');
  const host = useStudioHost();
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<RawSearchMode>('hybrid');
  const [granularity, setGranularity] = useState<RawSearchGranularity>('chapter');
  const [surface, setSurface] = useState<RawSearchSurface>('canon');
  const [limit, setLimit] = useState<number>(20);
  const debouncedQuery = useDebouncedValue(input, 250);
  const { isOwner, indexDrafts, isIndexing, result: indexResult, error: indexError } =
    useIndexDrafts(bookId);
  const effectiveSurface: RawSearchSurface = isOwner ? surface : 'canon';
  const { hits, disabled, isFetching, error, degraded } = useRawSearch(
    bookId, debouncedQuery, { mode, granularity, limit, surface: effectiveSurface },
  );
  const isDegraded = Object.keys(degraded).length > 0;

  // DOCK-7 — open the sibling `book-reader` dock panel, never a route push. BookReaderPanel
  // has no block-scroll param today (see file header) — this is an accepted v1 limitation.
  const onJump = (chapterId: string) => {
    host.openPanel('book-reader', { params: { bookId, chapterId } });
  };

  return (
    <div className="flex h-full flex-col gap-2 p-2" data-testid="chapter-browser-content-view">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('placeholder')}
            aria-label={t('placeholder')}
            data-testid="chapter-browser-content-input"
            className="w-full rounded-md border bg-background py-1.5 pl-8 pr-2 text-[12.5px] placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
        <div className="flex rounded-md border p-0.5" role="group" aria-label={t('mode_label')}>
          {MODES.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              data-testid={`chapter-browser-content-mode-${m}`}
              className={cn(
                'rounded px-2 py-1 text-[11px] font-medium transition-colors',
                mode === m ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(`mode_${m}`)}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
          {t('limit_label')}
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            data-testid="chapter-browser-content-limit"
            className="rounded-md border bg-background px-1 py-1 text-[11px] focus:outline-none focus:ring-2 focus:ring-ring/40"
          >
            {LIMITS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex items-center justify-between gap-2">
        <div className="flex rounded-md border p-0.5" role="group" aria-label={t('granularity_label')}>
          {GRANULARITIES.map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGranularity(g)}
              aria-pressed={granularity === g}
              title={t(`granularity_${g}_hint`)}
              data-testid={`chapter-browser-content-granularity-${g}`}
              className={cn(
                'rounded px-2 py-1 text-[11px] font-medium transition-colors',
                granularity === g ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(`granularity_${g}`)}
            </button>
          ))}
        </div>

        {isOwner && (
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border p-0.5" role="group" aria-label={t('surface_label')}>
              {SURFACES.map((sf) => (
                <button
                  key={sf}
                  type="button"
                  onClick={() => setSurface(sf)}
                  aria-pressed={surface === sf}
                  title={t(`surface_${sf}_hint`)}
                  data-testid={`chapter-browser-content-surface-${sf}`}
                  className={cn(
                    'rounded px-2 py-1 text-[11px] font-medium transition-colors',
                    surface === sf ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t(`surface_${sf}`)}
                </button>
              ))}
            </div>
            {indexResult && !indexError && (
              <span className="text-[10.5px] text-muted-foreground" data-testid="chapter-browser-content-index-drafts-result">
                {t('index_drafts_done', { indexed: indexResult.indexed, chapters: indexResult.chapters })}
              </span>
            )}
            {indexError && (
              <span className="text-[10.5px] text-destructive" data-testid="chapter-browser-content-index-drafts-error">
                {t('index_drafts_error')}
              </span>
            )}
            <button
              type="button"
              onClick={() => indexDrafts()}
              disabled={isIndexing}
              title={t('index_drafts_hint')}
              data-testid="chapter-browser-content-index-drafts"
              className="rounded-md border px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
            >
              {isIndexing ? t('index_drafts_busy') : t('index_drafts')}
            </button>
          </div>
        )}
      </div>

      {isDegraded && !error && (
        <p className="text-[11px] text-amber-600 dark:text-amber-400" data-testid="chapter-browser-content-degraded">
          {t('degraded')}
        </p>
      )}
      {error && (
        <p className="text-[12px] text-destructive" role="alert" data-testid="chapter-browser-content-error">
          {t('error')}
        </p>
      )}
      {!error && disabled && (
        <p className="text-[12px] text-muted-foreground" data-testid="chapter-browser-content-hint">
          {t('hint')}
        </p>
      )}
      {!error && !disabled && isFetching && hits.length === 0 && (
        <p className="text-[12px] text-muted-foreground" data-testid="chapter-browser-content-loading">
          {t('loading')}
        </p>
      )}
      {!error && !disabled && !isFetching && hits.length === 0 && (
        <p className="text-[12px] text-muted-foreground" data-testid="chapter-browser-content-empty">
          {t('no_results')}
        </p>
      )}
      {hits.length > 0 && (
        <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto" data-testid="chapter-browser-content-results">
          {hits.map((hit) => (
            <ChapterBrowserSnippetCard
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
