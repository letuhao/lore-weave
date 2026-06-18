import { useTranslation } from 'react-i18next';

import type { Job } from '../../types';
import { buildActivity, formatRelative } from '../../lib';

/** Activity timeline (live) — derived from the job's status + timestamps, newest
 *  first. Updates live via the SSE overlay (the caller passes the overlaid job). */
export function JobActivityTimeline({ job }: { job: Job }) {
  const { t } = useTranslation('jobs');
  const entries = buildActivity(job);
  if (entries.length === 0) return null;

  return (
    <div className="rounded-xl border bg-card">
      <div className="border-b px-4 py-3 text-sm font-semibold">
        {t('detail.activity', { defaultValue: 'Activity (live)' })}
      </div>
      <ul className="p-4 text-sm">
        {entries.map((e, i) => (
          <li key={`${e.at}-${i}`} className={`flex gap-3 py-1.5 ${i < entries.length - 1 ? 'border-b' : ''}`}>
            <span className="w-28 shrink-0 text-xs tabular-nums text-muted-foreground">
              {formatRelative(e.at)}
            </span>
            <span className={e.error ? 'text-destructive' : ''}>
              {t(e.messageKey, { defaultValue: e.defaultMessage })}
              {e.error ? ` — ${e.error}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
