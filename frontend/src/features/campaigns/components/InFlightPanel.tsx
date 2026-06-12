import { useTranslation } from 'react-i18next';
import { useInFlightChapters } from '../hooks/useCampaignQueries';
import type { CampaignChapter } from '../types';

/** Which driver-dispatched stages of a chapter are in flight right now. Only
 *  knowledge + translation are dispatched (eval is observed, never 'dispatched').
 *  Pure → unit-tested. */
export function inFlightStages(c: CampaignChapter): string[] {
  const stages: string[] = [];
  if (c.knowledge_status === 'dispatched') stages.push('knowledge');
  if (c.translation_status === 'dispatched') stages.push('translation');
  return stages;
}

/** D-FACTORY-INFLIGHT-PANEL (view) — a compact "Now processing" panel listing the
 *  chapters currently dispatched to a provider (the G3 stat shows only the count).
 *  Stage-level only (no batch/verify/backoff sub-step — not projected). Renders
 *  nothing when the campaign is terminal or nothing is in flight. */
export function InFlightPanel({ campaignId, active }: { campaignId: string; active: boolean }) {
  const { t } = useTranslation('campaigns');
  const q = useInFlightChapters(campaignId, active);
  const items = q.data?.items ?? [];
  // `total` is the true in-flight count; `items` is one page (limit 50). The driver
  // ceiling (driver_max_inflight_per_campaign, default 20) keeps total ≤ the page in
  // practice, but if it's raised above the page size we surface the overflow rather
  // than silently truncate.
  const total = q.data?.total ?? items.length;
  if (!active || total === 0) return null;
  const overflow = total - items.length;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-blue-500/30 bg-blue-500/5 p-3">
      <span className="text-sm font-medium text-blue-700 dark:text-blue-400">
        {t('monitor.nowProcessing', { defaultValue: 'Now processing ({{count}})', count: total })}
      </span>
      <div className="flex flex-wrap gap-1.5">
        {items.flatMap((c) =>
          inFlightStages(c).map((stage) => (
            <span key={`${c.chapter_id}-${stage}`}
              className="inline-flex items-center gap-1 rounded bg-blue-500/15 px-1.5 py-0.5 text-[11px] text-blue-700 dark:text-blue-300">
              <span className="font-medium">{t('monitor.chapterShort', { defaultValue: 'ch.{{sort}}', sort: c.chapter_sort })}</span>
              <span className="text-blue-600/70 dark:text-blue-400/70">· {stage}</span>
            </span>
          )),
        )}
        {overflow > 0 && (
          <span className="inline-flex items-center rounded bg-blue-500/10 px-1.5 py-0.5 text-[11px] text-blue-600/80 dark:text-blue-400/80">
            {t('monitor.inFlightMore', { defaultValue: '+{{count}} more', count: overflow })}
          </span>
        )}
      </div>
    </div>
  );
}
