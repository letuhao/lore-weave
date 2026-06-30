import type { TemporalSurfaceProps } from './CanonicalCard';

/** STUB — replaced by X6c agent. Change timeline w/ citations: the entity's fact-change feed (useTimeline). */
export function ChangeTimelinePanel({ entityId }: TemporalSurfaceProps) {
  return (
    <section data-testid="change-timeline" className="text-[12px] text-muted-foreground">
      Change timeline (entity {entityId.slice(0, 8)}) — coming soon
    </section>
  );
}
