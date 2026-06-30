import { useAsOf } from '../context/AsOfContext';

export interface TemporalSurfaceProps {
  bookId: string;
  entityId: string;
}

/** STUB — replaced by X6c agent. Canonical card: the entity's as-of folded canonical (useCanonical). */
export function CanonicalCard({ bookId, entityId }: TemporalSurfaceProps) {
  const { asOf } = useAsOf();
  return (
    <section data-testid="canonical-card" className="text-[12px] text-muted-foreground">
      Canonical (entity {entityId.slice(0, 8)}, as-of {asOf ?? 'head'}) — coming soon
    </section>
  );
}
