import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';
import type { GraphStats } from '../../types/projectState';

interface Props {
  stats: GraphStats;
  onExtractNew: () => void;
  onRebuild: () => void;
  onChangeModel: () => void;
  onDeleteGraph: () => void;
  onDisable: () => void;
  // C6 (G6 / KN-2 / KN-20) — when the card is hosted in the project-detail
  // shell, this deep-links into the shell's graph/entities sub-section.
  // Absent (flat ProjectsTab list) ⇒ the CTA + clickable stats are hidden.
  onExploreGraph?: () => void;
}

export function CompleteCard({
  stats,
  onExtractNew,
  onRebuild,
  onChangeModel,
  onDeleteGraph,
  onDisable,
  onExploreGraph,
}: Props) {
  const { t } = useTranslation('knowledge');
  // C6 — clickable stats deep-link into the shell's entities/graph view.
  // Only interactive when an onExploreGraph handler is supplied; in the
  // flat list it degrades to plain text.
  const statsLine = (
    <>
      {t('projects.state.cards.complete.stats', {
        entities: stats.entity_count,
        facts: stats.fact_count,
        events: stats.event_count,
        passages: stats.passage_count,
      })}
    </>
  );
  return (
    <StateCardShell label={t('projects.state.labels.complete')}>
      {onExploreGraph ? (
        <button
          type="button"
          onClick={onExploreGraph}
          className="text-left text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          data-testid="complete-clickable-stats"
        >
          {statsLine}
        </button>
      ) : (
        <p className="text-muted-foreground">{statsLine}</p>
      )}
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.complete.lastExtracted', {
          date: stats.last_extracted_at.slice(0, 10),
        })}
      </p>
      <div className="flex flex-wrap gap-2 pt-1">
        {onExploreGraph && (
          <StateActionButton
            variant="primary"
            onClick={onExploreGraph}
            data-testid="complete-explore-graph"
          >
            {t('projects.state.actions.exploreGraph')}
          </StateActionButton>
        )}
        <StateActionButton variant="primary" onClick={onExtractNew}>
          {t('projects.state.actions.extractNew')}
        </StateActionButton>
        <StateActionButton onClick={onRebuild}>
          {t('projects.state.actions.rebuild')}
        </StateActionButton>
        <StateActionButton onClick={onChangeModel}>
          {t('projects.state.actions.changeModel')}
        </StateActionButton>
        <StateActionButton variant="destructive" onClick={onDeleteGraph}>
          {t('projects.state.actions.deleteGraph')}
        </StateActionButton>
        <StateActionButton onClick={onDisable}>
          {t('projects.state.actions.disable')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
