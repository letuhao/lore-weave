import { isTerminal, type Job, type JobSseEvent, type JobStatus } from './types';

const ts = (s: string | null | undefined): number => (s ? Date.parse(s) : 0);

/** Overlay a live SSE event onto a fetched row when the event is at least as
 *  fresh. Compares parsed epoch ms (NOT lexicographically) so a serialization
 *  drift between the list's `updated_at` and the SSE's `occurred_at` — e.g. a `Z`
 *  vs `+00:00` suffix — can't silently mis-order and show stale data. The SSE
 *  frame lacks created_at/child_count, so we spread it over the base (keeps those). */
export function effectiveJob(base: Job, live: JobSseEvent | undefined): Job {
  if (!live) return base;
  if (ts(live.updated_at) >= ts(base.updated_at)) {
    // COALESCE the usage fields, mirroring the backend projection: a terminal/late
    // event carries model & params as null (they're emitted only on create), so a
    // naive spread would null them out in the UI until the next refetch. Keep the
    // base's value when the live one is null; a non-null live value (e.g. cost/
    // tokens growing on completion) still wins.
    return {
      ...base,
      ...live,
      model: live.model ?? base.model,
      cost_usd: live.cost_usd ?? base.cost_usd,
      tokens_in: live.tokens_in ?? base.tokens_in,
      tokens_out: live.tokens_out ?? base.tokens_out,
      params: live.params ?? base.params,
    };
  }
  return base;
}

/** Percent complete for a progress bar, or null when there's nothing to show.
 *  Guards a MISSING `total` (book_import emits {done} with no total — it doesn't know the
 *  chapter count upfront): `undefined <= 0` is false, so without the `!progress.total` check
 *  this would compute done/undefined = NaN and render a `width: NaN%` bar + "N/undefined". */
export function progressPct(progress: Job['progress']): number | null {
  if (!progress || !progress.total || progress.total <= 0) return null;
  return Math.min(100, Math.round((progress.done / progress.total) * 100));
}

/** Cost as a $ string. null → null (caller renders an em-dash). A real $0 shows as
 *  "$0.00" (reliable zero — e.g. failed-before-spend — not "unknown"). Sub-cent
 *  nonzero costs use 4 decimals so they don't collapse to "$0.00". */
export function formatCost(usd: number | null | undefined): string | null {
  if (usd == null) return null;
  if (usd > 0 && usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

/** Compact token count: 1234 → "1.2k", 1_200_000 → "1.2M". null → null. The 999_500
 *  cutoff (not 1_000_000) avoids a rounding artifact: 999_999/1000 → toFixed(0) = "1000"
 *  would render the nonsense "1000k" instead of "1.0M". */
export function formatTokens(n: number | null | undefined): string | null {
  if (n == null) return null;
  if (n < 1000) return String(n);
  if (n < 999_500) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

/** "1.2k → 240k" token pair, or null when BOTH are absent (one-sided still renders). */
export function formatTokenPair(
  tokensIn: number | null | undefined,
  tokensOut: number | null | undefined,
): string | null {
  if (tokensIn == null && tokensOut == null) return null;
  return `${formatTokens(tokensIn) ?? '0'} → ${formatTokens(tokensOut) ?? '0'}`;
}

/** Coarse relative time ("just now", "5m ago", "2h ago", "3d ago"). null → null. */
export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string | null {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  const s = Math.max(0, Math.round((now - then) / 1000));
  if (s < 45) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

/** One activity-timeline entry, newest first. `at` is an ISO timestamp; `messageKey`
 *  is an i18n key the view localizes (with `defaultValue`); `error` rides on a
 *  failed entry. */
export interface ActivityEntry {
  at: string;
  messageKey: string;
  defaultMessage: string;
  error?: string;
}

/** Derive a job's activity timeline from its own fields (created_at → current
 *  status@updated_at → live detail), newest-first. Deterministic and re-renders
 *  live via the SSE overlay — no event accumulation, no effect. Full intermediate
 *  history (pause/resume) is a backend activity-log concern (deferred). */
export function buildActivity(job: Job): ActivityEntry[] {
  const out: ActivityEntry[] = [];
  const terminal = isTerminal(job.status);

  // The live "now" line for a running job (its detail_status), newest.
  if (!terminal && job.detail_status && job.updated_at) {
    out.push({ at: job.updated_at, messageKey: 'activity.detail', defaultMessage: job.detail_status });
  }

  // The current-status transition at updated_at (skip 'pending' — that's "created").
  if (job.updated_at && job.status !== 'pending') {
    const labels: Record<JobStatus, [string, string]> = {
      pending: ['activity.pending', 'Queued'],
      running: ['activity.running', 'Running'],
      paused: ['activity.paused', 'Paused'],
      cancelling: ['activity.cancelling', 'Cancelling'],
      completed: ['activity.completed', 'Completed'],
      failed: ['activity.failed', 'Failed'],
      cancelled: ['activity.cancelled', 'Cancelled'],
    };
    const [key, def] = labels[job.status];
    out.push({ at: job.updated_at, messageKey: key, defaultMessage: def, error: job.error?.message });
  }

  // Created — oldest.
  if (job.created_at) {
    out.push({ at: job.created_at, messageKey: 'activity.created', defaultMessage: 'Created' });
  }
  return out;
}

/** Human duration between two ISO timestamps ("41s", "3m 12s", "2d 4h"). Returns
 *  null when start/end are missing or end precedes start. */
export function formatDuration(
  startIso: string | null | undefined,
  endIso: string | null | undefined,
): string | null {
  if (!startIso || !endIso) return null;
  const start = Date.parse(startIso);
  const end = Date.parse(endIso);
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;
  let s = Math.round((end - start) / 1000);
  const d = Math.floor(s / 86400);
  s -= d * 86400;
  const h = Math.floor(s / 3600);
  s -= h * 3600;
  const m = Math.floor(s / 60);
  s -= m * 60;
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
