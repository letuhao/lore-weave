import type { TemporalSurfaceProps } from './CanonicalCard';

/** STUB — replaced by X6c agent. Per-episode translation (§7): the entity's as-of-N translated context. */
export function EpisodeTranslationPanel({ bookId, entityId }: TemporalSurfaceProps) {
  return (
    <section data-testid="episode-translation" className="text-[12px] text-muted-foreground">
      Per-episode translation (book {bookId.slice(0, 8)}, entity {entityId.slice(0, 8)}) — coming soon
    </section>
  );
}
