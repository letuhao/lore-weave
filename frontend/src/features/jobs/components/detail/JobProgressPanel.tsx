import { useTranslation } from 'react-i18next';

import type { Job } from '../../types';
import { isTerminal } from '../../types';
import { progressPct, formatDuration } from '../../lib';

/** Detail progress panel: a wide bar + elapsed / throughput / ETA derived from the
 *  progress counts and timestamps. Throughput & ETA only show for a live job with
 *  measurable progress (no contract field for in-flight count, so it's omitted). */
export function JobProgressPanel({ job }: { job: Job }) {
  const { t } = useTranslation('jobs');
  const pct = progressPct(job.progress);
  const terminal = isTerminal(job.status);

  const nowIso = new Date(Date.now()).toISOString();
  const elapsed = formatDuration(job.created_at, terminal ? job.updated_at : nowIso);

  // Throughput / ETA from done-per-elapsed (live, with progress only). `total` may be absent
  // (book_import emits done without a total) → no ETA, but throughput still works off `done`.
  let throughput: string | null = null;
  let eta: string | null = null;
  const total = job.progress?.total ?? 0;
  if (!terminal && job.progress && total > 0 && job.created_at) {
    const elapsedH = (Date.now() - Date.parse(job.created_at)) / 3_600_000;
    const rate = elapsedH > 0 ? job.progress.done / elapsedH : 0;
    if (rate > 0) {
      throughput = t('detail.throughputVal', { defaultValue: '~{{n}} /h', n: Math.round(rate) });
      const remaining = total - job.progress.done;
      if (remaining > 0) {
        const etaMs = (remaining / rate) * 3_600_000;
        eta = formatDuration(nowIso, new Date(Date.now() + etaMs).toISOString());
      }
    }
  }

  const stat = (labelKey: string, def: string, value: string | null) =>
    value ? (
      <div>
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {t(labelKey, { defaultValue: def })}
        </div>
        <div className="mt-0.5 tabular-nums">{value}</div>
      </div>
    ) : null;

  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">
          {job.detail_status || t('detail.progress', { defaultValue: 'Progress' })}
        </span>
        {pct != null && (
          <span className="tabular-nums">
            {pct}% · {job.progress!.done} / {job.progress!.total}
          </span>
        )}
      </div>
      {pct != null && (
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-8 text-sm">
        {stat('detail.elapsed', 'Elapsed', elapsed)}
        {stat('detail.throughput', 'Throughput', throughput)}
        {stat('detail.eta', 'ETA', eta)}
      </div>
    </div>
  );
}
