import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { useDebouncedValue } from '../../knowledge/hooks/useDebouncedValue';
import { useAsOf } from '../context/AsOfContext';
import { useRetrieve } from '../hooks/useTemporalReads';
import type { TemporalSurfaceProps } from './CanonicalCard';
import type { RetrievedSegment } from '../types';

// X6c — "Retrieval, not scroll." A debounced semantic search over this book's episodes/segments,
// pinned to the current as-of (story-time) so results reflect the entity's context at that point.
// Reads through the KAL via useRetrieve (POST /v1/kal/books/{id}/retrieve). The hook is enabled
// only when a non-empty query is present, so an empty box fires no network call.
//
// Honors temporal_capability: if the substrate can't honor as_of yet (temporal_unsupported), the
// results are current-state — we say so plainly rather than pretend the slider moved them.

/** True when the KG substrate cannot honor as_of (results are head/current-state). */
function isTemporalUnsupported(cap: { kg?: string } | undefined): boolean {
  return cap?.kg === 'temporal_unsupported';
}

function ScoreChip({ score }: { score: number }) {
  // Relevance shown as a compact 0–100 chip. The KAL score is an opaque similarity; we render the
  // raw value scaled to a percent for a quick eyeball-rank, not as a calibrated probability.
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  return (
    <span
      className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground"
      data-testid="retrieval-score"
    >
      {pct}%
    </span>
  );
}

function SegmentRow({ seg }: { seg: RetrievedSegment }) {
  const { t } = useTranslation('knowledge');
  const text = typeof seg.text === 'string' ? seg.text.trim() : '';
  return (
    <li
      className="space-y-1 rounded-md border px-3 py-2 text-[12px]"
      data-testid="retrieval-result"
    >
      <div className="flex items-start gap-2">
        <span className="min-w-0 flex-1 whitespace-pre-wrap leading-relaxed">
          {text || (
            <span className="italic text-muted-foreground">
              {t('temporal.retrieval.noText', '(no preview text)')}
            </span>
          )}
        </span>
        {typeof seg.score === 'number' && <ScoreChip score={seg.score} />}
      </div>
      {seg.chapter_id && (
        <p className="text-[10px] text-muted-foreground" data-testid="retrieval-chapter">
          {t('temporal.retrieval.chapter', 'Chapter {{chapter}}', { chapter: seg.chapter_id })}
        </p>
      )}
    </li>
  );
}

/** Retrieval-not-scroll: semantic top-K over episodes/segments at the current as-of. */
export function RetrievalPanel({ bookId }: TemporalSurfaceProps) {
  const { t } = useTranslation('knowledge');
  const { asOf } = useAsOf();
  const [raw, setRaw] = useState('');
  const query = useDebouncedValue(raw.trim(), 300);

  const { items, temporalCapability, isLoading, error } = useRetrieve(
    bookId,
    query ? { query, as_of: asOf } : null,
  );

  const hasQuery = query.length > 0;

  return (
    <section data-testid="retrieval-panel" className="space-y-3">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder={t('temporal.retrieval.placeholder', 'Search this book’s context…')}
          aria-label={t('temporal.retrieval.ariaLabel', 'Search retrieval')}
          className="w-full rounded-md border bg-background py-1.5 pl-8 pr-3 text-[12px] outline-none transition-colors focus:border-foreground/40"
          data-testid="retrieval-input"
        />
      </div>

      {hasQuery && isTemporalUnsupported(temporalCapability) && (
        <p
          className="rounded-md border border-dashed px-2.5 py-1.5 text-[10px] text-muted-foreground"
          data-testid="retrieval-temporal-note"
        >
          {t(
            'temporal.retrieval.currentStateNote',
            'Results are current-state (temporal retrieval not yet available).',
          )}
        </p>
      )}

      {!hasQuery && (
        <p
          className="rounded-md border border-dashed px-3 py-4 text-center text-[12px] text-muted-foreground"
          data-testid="retrieval-empty-prompt"
        >
          {t('temporal.retrieval.typeToSearch', "Type to search this entity’s context.")}
        </p>
      )}

      {hasQuery && isLoading && (
        <div className="space-y-2" data-testid="retrieval-loading">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-md border bg-muted/30" />
          ))}
        </div>
      )}

      {hasQuery && error && !isLoading && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="retrieval-error"
        >
          {t('temporal.retrieval.error', 'Search failed: {{error}}', { error: error.message })}
        </div>
      )}

      {hasQuery && !isLoading && !error && items.length === 0 && (
        <p
          className="rounded-md border border-dashed px-3 py-4 text-center text-[12px] text-muted-foreground"
          data-testid="retrieval-no-results"
        >
          {t('temporal.retrieval.noResults', 'No matching context found.')}
        </p>
      )}

      {hasQuery && !isLoading && !error && items.length > 0 && (
        <ul className="space-y-1.5" data-testid="retrieval-results">
          {items.map((seg, i) => (
            <SegmentRow key={seg.id ?? i} seg={seg} />
          ))}
        </ul>
      )}
    </section>
  );
}
