import { useTranslation } from 'react-i18next';
import { useCampaignActivity } from '../hooks/useCampaignQueries';

/** Compact relative time ("just now", "5s", "3m", "2h", "4d") from an ISO string.
 *  Pure → unit-tested. nowMs is injected so the test is deterministic. */
export function relTime(iso: string, nowMs: number): string {
  const diff = Math.max(0, nowMs - new Date(iso).getTime());
  const s = Math.floor(diff / 1000);
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

const STATUS_TONE: Record<string, string> = {
  done: 'text-green-600 dark:text-green-400',
  skipped: 'text-muted-foreground',
  dispatched: 'text-blue-600 dark:text-blue-400',
  failed: 'text-destructive',
};

/** D-FACTORY-INFLIGHT-LOG (view) — the monitor's recent-activity feed (newest first),
 *  one row per stage-status transition. Renders nothing when there's no activity yet.
 *  Stage-level only (sourced by the campaign_chapters trigger). */
export function ActivityLog({ campaignId, active }: { campaignId: string; active: boolean }) {
  const { t } = useTranslation('campaigns');
  const q = useCampaignActivity(campaignId, active);
  const items = q.data?.items ?? [];
  if (items.length === 0) return null;
  const now = Date.now();

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium">
        {t('monitor.activity', { defaultValue: 'Recent activity' })}
      </span>
      <ul className="flex flex-col divide-y rounded-md border text-[12px]">
        {items.map((a) => (
          <li key={a.id} className="flex items-center gap-2 px-3 py-1.5">
            <span className="w-10 shrink-0 tabular-nums text-muted-foreground">{relTime(a.created_at, now)}</span>
            <span className="font-medium">{t('monitor.chapterShort', { defaultValue: 'ch.{{sort}}', sort: a.chapter_sort })}</span>
            <span className="text-muted-foreground">· {a.stage} ·</span>
            <span className={STATUS_TONE[a.status] ?? ''}>{a.status}</span>
            {a.detail && (
              <span className="truncate text-destructive/80" title={a.detail}>— {a.detail}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
