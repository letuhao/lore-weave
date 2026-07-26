import { useTranslation } from 'react-i18next';
import { StateCardShell, StateActionButton, ProgressBar } from './shared';
import { ConcurrencyControl } from './ConcurrencyControl';
import { formatElapsed } from '../../lib/formatElapsed';
import type { ExtractionJobSummary } from '../../types/projectState';

interface Props {
  job: ExtractionJobSummary;
  onPause: () => void;
  onCancel: () => void;
  // C7 raise-cap (KN-7) — change the parallel-LLM cap in-flight.
  onSetConcurrency: (jobId: string, level: number) => void;
}

export function BuildingRunningCard({ job, onPause, onCancel, onSetConcurrency }: Props) {
  const { t } = useTranslation('knowledge');
  const spentLine = job.max_spend_usd
    ? t('projects.state.cards.building_running.spentOfBudget', {
        spent: job.cost_spent_usd,
        budget: job.max_spend_usd,
      })
    : t('projects.state.cards.building_running.spent', { spent: job.cost_spent_usd });

  // KN-9 (C7) — a running build is opaque without a "how long has this
  // been going" cue. Derive elapsed from started_at client-side (no BE);
  // null when the timestamp is missing/unparseable so we render nothing
  // rather than a bogus "NaN".
  const elapsed = formatElapsed(job.started_at);

  return (
    <StateCardShell label={t('projects.state.labels.building_running')}>
      <ProgressBar processed={job.items_processed} total={job.items_total} />
      <p className="text-[12px] text-muted-foreground">
        {t('projects.state.cards.building_running.progress', {
          processed: job.items_processed,
          total: job.items_total ?? '?',
        })}
      </p>
      {elapsed && (
        <p
          className="text-[12px] text-muted-foreground"
          data-testid="building-running-elapsed"
        >
          {t('projects.state.cards.building_running.elapsed', { elapsed })}
        </p>
      )}
      <p className="text-[12px] text-muted-foreground">{spentLine}</p>
      {/* #16 — a full build runs passes in STAGES (facts/summaries last); the
          aggregate item counter hides this, so a user who stops early thinks
          facts/summaries are missing. Make the staging explicit. */}
      <div
        className="rounded-md border bg-muted/30 px-2.5 py-2"
        data-testid="building-running-stages"
      >
        <p className="text-[11px] font-medium text-muted-foreground">
          {t('projects.state.cards.building_running.stagesTitle')}
        </p>
        <p className="mt-0.5 text-[11px]">
          {t('projects.state.cards.building_running.stages')}
        </p>
        <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
          {t('projects.state.cards.building_running.stagesNote')}
        </p>
      </div>
      <ConcurrencyControl
        jobId={job.job_id}
        current={job.concurrency_level}
        onSetConcurrency={onSetConcurrency}
      />
      <div className="flex gap-2 pt-1">
        <StateActionButton onClick={onPause}>
          {t('projects.state.actions.pause')}
        </StateActionButton>
        <StateActionButton variant="destructive" onClick={onCancel}>
          {t('projects.state.actions.cancel')}
        </StateActionButton>
      </div>
    </StateCardShell>
  );
}
