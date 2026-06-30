import { useTranslation } from 'react-i18next';
import { Languages } from 'lucide-react';
import { useAsOf } from '../context/AsOfContext';
import { useCanonical } from '../hooks/useTemporalReads';
import type { TemporalSurfaceProps } from './CanonicalCard';

// X6c — Per-episode / as-of translated context (spec §7).
//
// DATA-SOURCE DECISION: the KAL does NOT yet expose a per-entity translation read endpoint, and
// there is no existing FE source for an entity's *translated* as-of context (the `translation`
// feature works on chapter/segment versions, not on a folded entity snapshot). Rather than invent
// a backend call to a non-existent endpoint, this surface degrades honestly: it renders the
// entity's AS-OF folded canonical (useCanonical → the SAME read the CanonicalCard uses) as the
// temporal context, and carries a clear, non-alarming note that *translation* rendering will light
// up once the translation read surface lands. The component shape (props, layout, loading/error,
// the canonical content slot) is built so wiring a real translation read later is a small,
// localized change — swap the data hook + drop the pending note.

/** Per-episode translation (§7): the entity's as-of context, pending the translation read surface. */
export function EpisodeTranslationPanel({ bookId, entityId }: TemporalSurfaceProps) {
  const { t } = useTranslation('knowledge');
  const { asOf } = useAsOf();
  const { canonical, isLoading, error } = useCanonical(bookId, entityId, asOf);

  const asOfLabel =
    asOf === undefined
      ? t('temporal.translation.asOfHead', 'latest')
      : t('temporal.translation.asOfChapter', 'chapter {{n}}', { n: asOf });

  const content = canonical?.content?.trim() ?? '';

  return (
    <section data-testid="episode-translation" className="space-y-3">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
        <Languages className="h-3 w-3" aria-hidden />
        <span>{t('temporal.translation.title', 'Per-episode context')}</span>
        <span className="text-foreground/60" data-testid="episode-translation-asof">
          {t('temporal.translation.asOfLabel', 'as of {{label}}', { label: asOfLabel })}
        </span>
      </div>

      {/* Honest capability note — this surface shows the AS-OF canonical, not translated text yet. */}
      <p
        className="rounded-md border border-dashed px-2.5 py-1.5 text-[10px] text-muted-foreground"
        data-testid="episode-translation-pending-note"
      >
        {t(
          'temporal.translation.pendingNote',
          'Showing this entity’s as-of context. Per-episode translation will appear here once the translation read surface is available.',
        )}
      </p>

      {isLoading && (
        <div className="space-y-2" data-testid="episode-translation-loading">
          {[0, 1].map((i) => (
            <div key={i} className="h-4 animate-pulse rounded bg-muted/40" />
          ))}
        </div>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="episode-translation-error"
        >
          {t('temporal.translation.error', 'Failed to load context: {{error}}', {
            error: error.message,
          })}
        </div>
      )}

      {!isLoading && !error && (
        content ? (
          <p
            className="whitespace-pre-wrap text-[12px] leading-relaxed"
            data-testid="episode-translation-content"
          >
            {content}
          </p>
        ) : (
          <p
            className="rounded-md border border-dashed px-3 py-4 text-center text-[12px] text-muted-foreground"
            data-testid="episode-translation-empty"
          >
            {t('temporal.translation.empty', 'No as-of context available for this point in the story.')}
          </p>
        )
      )}
    </section>
  );
}
