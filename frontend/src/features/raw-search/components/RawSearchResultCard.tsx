import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { renderHighlight } from './renderHighlight';
import type { RawSearchHit } from '../types';

// Presentational raw-search result. Focusable button (Enter/Space) → jump.
// Logic/state lives in the parent panel; this component is display-only.

const SURFACE_CLASSES: Record<string, string> = {
  draft: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  canon: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
};

const clamp01 = (n: number): number => Math.max(0, Math.min(1, n));

export interface RawSearchResultCardProps {
  hit: RawSearchHit;
  onJump: (chapterId: string, pos?: number) => void;
}

export function RawSearchResultCard({ hit, onJump }: RawSearchResultCardProps) {
  const { t } = useTranslation('rawSearch');
  // Pass the lexical blockIndex (matches the reader's data-block-id) for precise
  // scroll. Semantic hits have only a chunkIndex (not a block index) → blockIndex
  // is undefined → the reader opens the chapter without scroll.
  const jump = () => onJump(hit.chapterId, hit.location.blockIndex);
  const relevancePct =
    hit.relevance != null ? Math.round(clamp01(hit.relevance) * 100) : null;
  return (
    <li data-testid="raw-search-result">
      {/* Native <button> activates onClick on both Enter and Space — no
          onKeyDown needed (a redundant one double-fires on Space). */}
      <button
        type="button"
        onClick={jump}
        className="grid w-full grid-cols-[auto_1fr] items-start gap-3 px-3 py-2.5 text-left text-[12px] transition-colors hover:bg-muted/50"
      >
        <span className="flex flex-col items-start gap-1">
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
              SURFACE_CLASSES[hit.surface] ?? 'bg-muted text-muted-foreground',
            )}
            data-testid="raw-search-surface"
          >
            {hit.surface}
          </span>
          <span
            className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground"
            data-testid="raw-search-matchtype"
          >
            {hit.matchType}
          </span>
        </span>
        <span className="min-w-0 flex-1">
          <span className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="truncate font-medium text-foreground/80">
              {hit.chapterTitle ?? `#${hit.sortOrder}`}
            </span>
            {hit.location.headingContext && (
              <span className="truncate">· {hit.location.headingContext}</span>
            )}
            {relevancePct != null && (
              // Thin relevance bar (E6) — fill = cross-encoder/lexical score.
              <span
                className="ml-auto flex shrink-0 items-center"
                role="meter"
                aria-label={`${t('relevance_label')} ${relevancePct}%`}
                aria-valuenow={relevancePct}
                aria-valuemin={0}
                aria-valuemax={100}
                title={`${relevancePct}%`}
                data-testid="raw-search-relevance"
              >
                <span className="h-1 w-10 overflow-hidden rounded-full bg-muted">
                  <span
                    className="block h-full rounded-full bg-primary/70"
                    style={{ width: `${relevancePct}%` }}
                  />
                </span>
              </span>
            )}
          </span>
          <span className="line-clamp-3 whitespace-pre-wrap break-words text-foreground">
            {renderHighlight(hit.snippet, hit.highlights)}
          </span>
        </span>
      </button>
    </li>
  );
}
