import type { TemporalSurfaceProps } from './CanonicalCard';

/** STUB — replaced by X6c agent. Diff view: entity state at the as-of ordinal vs the head (useFacts ×2). */
export function DiffViewPanel({ entityId }: TemporalSurfaceProps) {
  return (
    <section data-testid="diff-view" className="text-[12px] text-muted-foreground">
      Diff view (entity {entityId.slice(0, 8)}) — coming soon
    </section>
  );
}
