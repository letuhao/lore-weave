import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton } from './shared';
import type { CostEstimate } from '../../types/projectState';

interface Props {
  estimate: CostEstimate;
  onStart: () => void;
  onCancel: () => void;
}

export function ReadyToBuildCard({ estimate, onStart, onCancel }: Props) {
  const { t } = useTranslation('knowledge');
  const minutes = Math.round(estimate.estimated_duration_seconds / 60);
  const durationLine =
    minutes >= 1
      ? t('projects.state.cards.ready_to_build.durationMin', { n: minutes })
      : t('projects.state.cards.ready_to_build.durationSec', {
          n: estimate.estimated_duration_seconds,
        });
  return (
    <StateCardShell label={t('projects.state.labels.ready_to_build')}>
      <p className="text-muted-foreground">
        {t('projects.state.cards.ready_to_build.hint', {
          low: estimate.estimated_cost_usd_low,
          high: estimate.estimated_cost_usd_high,
          chapters: estimate.items.chapters,
          turns: estimate.items.chat_turns,
          tokens: estimate.estimated_tokens.toLocaleString(),
        })}
      </p>
      <p className="text-[12px] text-muted-foreground">{durationLine}</p>
      <div className="flex gap-2 pt-1">
        <StateActionButton variant="primary" onClick={onStart}>
          {t('projects.state.actions.start')}
        </StateActionButton>
        <StateActionButton onClick={onCancel}>
          {t('projects.state.actions.cancel')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
