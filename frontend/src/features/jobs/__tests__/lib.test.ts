import { describe, it, expect } from 'vitest';
import { effectiveJob, progressPct } from '../lib';
import type { Job, JobSseEvent } from '../types';

const base: Job = {
  service: 'knowledge', job_id: 'j1', owner_user_id: 'u', kind: 'extraction',
  status: 'running', parent_job_id: null, detail_status: 'ch 1/10',
  progress: { done: 1, total: 10 }, control_caps: ['pause', 'cancel'], title: 't',
  error: null, created_at: '2026-06-16T00:00:00+00:00', updated_at: '2026-06-16T00:00:00+00:00',
  child_count: 4,
};

describe('effectiveJob', () => {
  it('overlays a fresher live event onto the base row', () => {
    const live: JobSseEvent = {
      ...base, status: 'paused', control_caps: ['resume', 'cancel'],
      progress: { done: 5, total: 10 }, updated_at: '2026-06-16T00:01:00+00:00',
    };
    const out = effectiveJob(base, live);
    expect(out.status).toBe('paused');
    expect(out.control_caps).toEqual(['resume', 'cancel']);
    expect(out.progress).toEqual({ done: 5, total: 10 });
    // created_at / child_count are not on the SSE frame → preserved from base.
    expect(out.created_at).toBe('2026-06-16T00:00:00+00:00');
    expect(out.child_count).toBe(4);
  });

  it('ignores a stale live event (older updated_at)', () => {
    const stale: JobSseEvent = { ...base, status: 'pending', updated_at: '2026-06-15T00:00:00+00:00' };
    expect(effectiveJob(base, stale).status).toBe('running');
  });

  it('returns the base unchanged when there is no live event', () => {
    expect(effectiveJob(base, undefined)).toBe(base);
  });

  it('orders by real time, not string bytes (Z vs +00:00 / fractional drift)', () => {
    // base is newer by 500ms but, lexicographically, the older live string
    // ("…00Z") sorts ABOVE base ("…00.500+00:00") — a byte compare would wrongly
    // apply the stale live event. Epoch compare keeps the newer base.
    const newerBase: Job = { ...base, status: 'running', updated_at: '2026-06-16T00:00:00.500+00:00' };
    const olderLive: JobSseEvent = { ...base, status: 'pending', updated_at: '2026-06-16T00:00:00Z' };
    expect(effectiveJob(newerBase, olderLive).status).toBe('running');
  });
});

describe('progressPct', () => {
  it('is null when progress is null', () => expect(progressPct(null)).toBeNull());
  it('is null when total is 0 (avoids divide-by-zero)', () =>
    expect(progressPct({ done: 0, total: 0 })).toBeNull());
  it('rounds the percentage', () => expect(progressPct({ done: 3, total: 10 })).toBe(30));
  it('caps at 100', () => expect(progressPct({ done: 11, total: 10 })).toBe(100));
});
