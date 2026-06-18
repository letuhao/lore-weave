import type { Job } from '../types';
import { progressPct } from '../lib';

/** Null-safe progress line: a bar + done/total when progress is present, plus the
 *  service-native detail_status passthrough. Renders nothing if both are absent. */
export function JobProgress({
  progress,
  detailStatus,
}: {
  progress: Job['progress'];
  detailStatus: string | null;
}) {
  const pct = progressPct(progress);
  if (pct == null && !detailStatus) return null;
  return (
    <div className="flex flex-col gap-1">
      {pct != null && (
        <div className="flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full bg-blue-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
            {progress!.done}/{progress!.total}
          </span>
        </div>
      )}
      {detailStatus && <span className="text-[11px] text-muted-foreground">{detailStatus}</span>}
    </div>
  );
}
