import type { ExtractionJobWire } from '../api';

// K19b.3 — client-side ETA for an active extraction job.
//
// The BE doesn't ship a `progress_rate` field on ExtractionJob, so we
// derive items-per-second ourselves by diffing `items_processed`
// across consecutive hook calls (which happen every 2s via
// `useExtractionJobs` polling). An exponentially-weighted moving
// average damps the per-poll jitter that a single chapter's LLM call
// introduces; without EMA, a 30s chapter-extraction would show
// minutesRemaining oscillating between "0.5 min" and "nothing this
// poll".
//
// Clears D-K19b.4-01 (was: "ETA deferred, needs BE field or client EMA").

/** Blend weight for fresh rate samples. α=0.3 → effective time
 *  constant ≈ 3.3 samples ≈ 7s at our 2s poll cadence, which is slow
 *  enough to smooth a chapter-long LLM call but fast enough to react
 *  to real step changes (e.g. a paused job resuming). */
const ALPHA = 0.3;

/** Wall-clock tolerance: if two consecutive samples are >60s apart
 *  (user backgrounded the tab / network drop), treat as a fresh start
 *  rather than averaging across the gap. */
const STALE_SAMPLE_MS = 60_000;

interface Sample {
  lastProcessed: number;
  lastSeenMs: number;
  emaItemsPerSec: number;
}

export interface UseJobProgressRateResult {
  /** `null` when we can't compute (status≠running, no total, no
   *  prior sample, rate=0). Consumers should hide the ETA line when
   *  null, not render "—" for every non-running job. */
  minutesRemaining: number | null;
  itemsPerSecond: number | null;
}

// Module-scoped so all hook instances share the same per-job memory.
// This matters when ExtractionJobsTab + JobDetailPanel both call the
// hook on the same job_id — we want them to converge on the same EMA.
// Map leak is bounded: ~30 bytes per job_id, typical session stays
// under 100 jobs, session lifetime ends on page refresh.
// TODO: if real users accumulate >10k historical jobs in a long session,
// swap to an LRU of size ~500.
const samplesByJob = new Map<string, Sample>();

export function useJobProgressRate(
  job: ExtractionJobWire | null,
): UseJobProgressRateResult {
  if (!job || job.status !== 'running' || job.items_total == null) {
    return { minutesRemaining: null, itemsPerSecond: null };
  }

  const now = Date.now();
  const prior = samplesByJob.get(job.job_id);

  // First sample for this job — seed and return null (one sample isn't
  // a rate). Next poll will compute real delta.
  if (!prior) {
    samplesByJob.set(job.job_id, {
      lastProcessed: job.items_processed,
      lastSeenMs: now,
      emaItemsPerSec: 0,
    });
    return { minutesRemaining: null, itemsPerSecond: null };
  }

  const elapsedMs = now - prior.lastSeenMs;
  const deltaItems = job.items_processed - prior.lastProcessed;

  // Stale sample → reseed from current values without averaging across
  // a tab-backgrounded gap.
  if (elapsedMs > STALE_SAMPLE_MS) {
    samplesByJob.set(job.job_id, {
      lastProcessed: job.items_processed,
      lastSeenMs: now,
      emaItemsPerSec: 0,
    });
    return { minutesRemaining: null, itemsPerSecond: null };
  }

  // No progress since last poll → update timestamp so the next poll's
  // elapsedMs is measured from the latest zero-delta sample, not a
  // stale one. Preserves existing EMA so a brief stall doesn't trash
  // the rate estimate.
  if (deltaItems <= 0 || elapsedMs <= 0) {
    samplesByJob.set(job.job_id, {
      lastProcessed: job.items_processed,
      lastSeenMs: now,
      emaItemsPerSec: prior.emaItemsPerSec,
    });
    if (prior.emaItemsPerSec <= 0) {
      return { minutesRemaining: null, itemsPerSecond: null };
    }
    const remainingItems = job.items_total - job.items_processed;
    const minutes = remainingItems / prior.emaItemsPerSec / 60;
    return {
      minutesRemaining: minutes > 0 ? minutes : null,
      itemsPerSecond: prior.emaItemsPerSec,
    };
  }

  const instRate = (deltaItems / elapsedMs) * 1000; // items per second
  // On first real sample (prior emaItemsPerSec=0), take the raw
  // instantaneous rate; otherwise blend via EMA.
  const ema =
    prior.emaItemsPerSec <= 0
      ? instRate
      : ALPHA * instRate + (1 - ALPHA) * prior.emaItemsPerSec;

  samplesByJob.set(job.job_id, {
    lastProcessed: job.items_processed,
    lastSeenMs: now,
    emaItemsPerSec: ema,
  });

  const remainingItems = job.items_total - job.items_processed;
  const minutes = ema > 0 ? remainingItems / ema / 60 : null;

  return {
    minutesRemaining: minutes != null && minutes > 0 ? minutes : null,
    itemsPerSecond: ema,
  };
}

/** Test-only escape hatch: reset the module-scoped sample map between
 *  tests so each test starts with a clean slate. Not exported in the
 *  production barrel. */
export function __resetSamplesForTests(): void {
  samplesByJob.clear();
}
