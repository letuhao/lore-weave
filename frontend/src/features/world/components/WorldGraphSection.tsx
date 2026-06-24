import { useTranslation } from 'react-i18next';
import { WorldRollupGraph } from './WorldRollupGraph';

interface WorldGraphSectionProps {
  /** The world whose member books roll up into one canon graph. */
  worldId: string | undefined;
}

// W5 (G4, decision ⑤) — the world graph is now the ROLLUP: a union of every
// member book's canon subgraph + the world-level (bible) project, read from
// W2's `GET /worlds/{id}/subgraph`. This REPLACES the old bible-only embed
// (which only ever showed the bible book's own project). Read-only; when the
// world has no knowledge yet, WorldRollupGraph renders its own empty state.
export function WorldGraphSection({ worldId }: WorldGraphSectionProps) {
  const { t } = useTranslation('world');

  return (
    <section className="space-y-2" data-testid="world-graph-section">
      <h2 className="font-medium">{t('graph.title', { defaultValue: 'World graph' })}</h2>
      <p className="text-xs text-muted-foreground">
        {t('graph.rollupSubtitle', {
          defaultValue:
            'A read-only roll-up of every member book’s canon graph, rendered together as per-book islands.',
        })}
      </p>
      <WorldRollupGraph worldId={worldId} />
    </section>
  );
}
