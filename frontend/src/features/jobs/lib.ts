import type { Job, JobSseEvent } from './types';

const ts = (s: string | null | undefined): number => (s ? Date.parse(s) : 0);

/** Overlay a live SSE event onto a fetched row when the event is at least as
 *  fresh. Compares parsed epoch ms (NOT lexicographically) so a serialization
 *  drift between the list's `updated_at` and the SSE's `occurred_at` — e.g. a `Z`
 *  vs `+00:00` suffix — can't silently mis-order and show stale data. The SSE
 *  frame lacks created_at/child_count, so we spread it over the base (keeps those). */
export function effectiveJob(base: Job, live: JobSseEvent | undefined): Job {
  if (!live) return base;
  if (ts(live.updated_at) >= ts(base.updated_at)) {
    return { ...base, ...live };
  }
  return base;
}

/** Percent complete for a progress bar, or null when there's nothing to show. */
export function progressPct(progress: Job['progress']): number | null {
  if (!progress || progress.total <= 0) return null;
  return Math.min(100, Math.round((progress.done / progress.total) * 100));
}
