import { useTranslation } from 'react-i18next';

import { useJobsFairness } from '../hooks/useJobsFairness';
import type { JobFairnessLane } from '../types';

const LANE_LABEL: Record<string, string> = {
  translation: 'fairness.lane.translation',
  knowledge: 'fairness.lane.knowledge',
  lore_enrichment: 'fairness.lane.loreEnrichment',
};

/** P5 — surfaces the owner's fair-scheduling depth ("N queued behind your cap"). Renders
 *  nothing when P5 is off OR the owner has no active lane (the common case) — a passive
 *  banner that only appears under contention. `running/cap` per lane; `queued` when > 0
 *  (translation's PUSH ready queue; knowledge/lore-enrichment back-pressure differently). */
export function FairnessBanner() {
  const { t } = useTranslation('jobs');
  const { data } = useJobsFairness();
  if (!data?.enabled || data.lanes.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-amber-700 dark:text-amber-400">
          {t('fairness.title', { defaultValue: 'Fair scheduling' })}
        </span>
        {data.lanes.map((l: JobFairnessLane) => (
          <span key={l.lane} className="flex items-center gap-1.5 text-muted-foreground">
            <span className="font-medium text-foreground">
              {t(LANE_LABEL[l.lane] ?? '', { defaultValue: l.lane })}
            </span>
            <span className="tabular-nums">
              {t('fairness.running', {
                defaultValue: '{{running}}/{{cap}} running',
                running: l.running,
                cap: l.cap,
              })}
            </span>
            {l.queued > 0 && (
              <span className="tabular-nums text-amber-700 dark:text-amber-400">
                {t('fairness.queued', { defaultValue: '· {{queued}} queued', queued: l.queued })}
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
