import { useTranslation } from 'react-i18next';
import type { CampaignProgress, StageCounts } from '../types';

const STAGES: Array<keyof CampaignProgress['stages']> = ['knowledge', 'translation', 'eval'];

/** S6 (view) — per-stage progress bar (done / failed / in-progress) from the
 *  lightweight progress counts. */
export function StageProgress({ stages }: { stages: CampaignProgress['stages'] }) {
  const { t } = useTranslation('campaigns');
  const label: Record<string, string> = {
    knowledge: t('monitor.stage.knowledge', { defaultValue: 'Knowledge' }),
    translation: t('monitor.stage.translation', { defaultValue: 'Translation' }),
    eval: t('monitor.stage.eval', { defaultValue: 'Eval' }),
  };
  return (
    <div className="flex flex-col gap-3">
      {STAGES.map((s) => <StageRow key={s} label={label[s]} counts={stages[s]} />)}
    </div>
  );
}

function StageRow({ label, counts }: { label: string; counts: StageCounts }) {
  const { t } = useTranslation('campaigns');
  const { total, done, failed } = counts;
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between text-xs">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">
          {t('monitor.stageCounts', {
            defaultValue: '{{done}}/{{total}} done · {{failed}} failed',
            done, total, failed,
          })}
        </span>
      </div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full bg-green-500" style={{ width: `${pct(done)}%` }} />
        <div className="h-full bg-destructive" style={{ width: `${pct(failed)}%` }} />
      </div>
    </div>
  );
}
