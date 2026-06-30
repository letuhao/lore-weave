import type { TemporalSurfaceProps } from './CanonicalCard';

/** STUB — replaced by X6c agent. Retrieval-not-scroll: semantic top-K over episodes/segments (useRetrieve). */
export function RetrievalPanel({ bookId, entityId }: TemporalSurfaceProps) {
  return (
    <section data-testid="retrieval-panel" className="text-[12px] text-muted-foreground">
      Retrieval (book {bookId.slice(0, 8)}, entity {entityId.slice(0, 8)}) — coming soon
    </section>
  );
}
