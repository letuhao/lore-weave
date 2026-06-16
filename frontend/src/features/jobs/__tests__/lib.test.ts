import { describe, it, expect } from 'vitest';
import {
  effectiveJob,
  progressPct,
  formatCost,
  formatTokens,
  formatTokenPair,
  formatRelative,
  formatDuration,
  buildActivity,
} from '../lib';
import type { Job, JobSseEvent } from '../types';

const base: Job = {
  service: 'knowledge', job_id: 'j1', owner_user_id: 'u', kind: 'extraction',
  status: 'running', parent_job_id: null, detail_status: 'ch 1/10',
  progress: { done: 1, total: 10 }, control_caps: ['pause', 'cancel'], title: 't',
  error: null, model: null, cost_usd: null, tokens_in: null, tokens_out: null, params: null,
  created_at: '2026-06-16T00:00:00+00:00', updated_at: '2026-06-16T00:00:00+00:00',
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

  it('COALESCEs usage fields — a terminal event with null model/params keeps them', () => {
    const withUsage: Job = {
      ...base, model: 'qwen', params: { targets: ['entities'] }, cost_usd: 1.0, tokens_in: 100, tokens_out: 50,
    };
    // Terminal event: status flips, cost/tokens grow, but model & params are null
    // (emitted only on create). The naive spread would null them out.
    const terminal: JobSseEvent = {
      ...withUsage, status: 'completed', model: null, params: null, cost_usd: 1.5,
      tokens_in: 200, tokens_out: 90, updated_at: '2026-06-16T00:02:00+00:00',
    };
    const out = effectiveJob(withUsage, terminal);
    expect(out.status).toBe('completed');
    expect(out.model).toBe('qwen'); // preserved (live null)
    expect(out.params).toEqual({ targets: ['entities'] }); // preserved (live null)
    expect(out.cost_usd).toBe(1.5); // non-null live wins
    expect(out.tokens_out).toBe(90);
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

describe('formatCost', () => {
  it('null → null (never a misleading $0)', () => expect(formatCost(null)).toBeNull());
  it('a real zero → $0.00', () => expect(formatCost(0)).toBe('$0.00'));
  it('normal cost → 2 decimals', () => expect(formatCost(3.181)).toBe('$3.18'));
  it('sub-cent nonzero → 4 decimals (no collapse to $0.00)', () =>
    expect(formatCost(0.0004)).toBe('$0.0004'));
});

describe('formatTokens / formatTokenPair', () => {
  it('null → null', () => expect(formatTokens(null)).toBeNull());
  it('< 1k verbatim', () => expect(formatTokens(742)).toBe('742'));
  it('thousands → k', () => expect(formatTokens(7417)).toBe('7.4k'));
  it('millions → M', () => expect(formatTokens(1_100_000)).toBe('1.1M'));
  it('pair joins with arrow, one-sided allowed', () =>
    expect(formatTokenPair(12000, 9000)).toBe('12k → 9.0k'));
  it('pair null when both absent', () => expect(formatTokenPair(null, null)).toBeNull());
  it('pair renders 0 for a missing side', () => expect(formatTokenPair(null, 9000)).toBe('0 → 9.0k'));
});

describe('formatRelative / formatDuration', () => {
  const now = Date.parse('2026-06-16T12:00:00Z');
  it('just now under 45s', () =>
    expect(formatRelative('2026-06-16T11:59:30Z', now)).toBe('just now'));
  it('minutes', () => expect(formatRelative('2026-06-16T11:30:00Z', now)).toBe('30m ago'));
  it('hours', () => expect(formatRelative('2026-06-16T09:00:00Z', now)).toBe('3h ago'));
  it('days', () => expect(formatRelative('2026-06-14T12:00:00Z', now)).toBe('2d ago'));
  it('null → null', () => expect(formatRelative(null)).toBeNull());
  it('duration seconds', () =>
    expect(formatDuration('2026-06-16T12:00:00Z', '2026-06-16T12:00:41Z')).toBe('41s'));
  it('duration m s', () =>
    expect(formatDuration('2026-06-16T12:00:00Z', '2026-06-16T12:03:12Z')).toBe('3m 12s'));
  it('duration d h', () =>
    expect(formatDuration('2026-06-14T08:00:00Z', '2026-06-16T12:00:00Z')).toBe('2d 4h'));
  it('null when end precedes start', () =>
    expect(formatDuration('2026-06-16T12:00:00Z', '2026-06-16T11:00:00Z')).toBeNull());
});

describe('buildActivity', () => {
  it('newest-first: detail (running) → status → created', () => {
    const out = buildActivity(base);
    expect(out.map((e) => e.messageKey)).toEqual(['activity.detail', 'activity.running', 'activity.created']);
    expect(out[0].defaultMessage).toBe('ch 1/10'); // detail_status passthrough
  });
  it('a failed job carries its error on the status entry', () => {
    const failed: Job = { ...base, status: 'failed', detail_status: null, error: { code: '429', message: 'rate limited' } };
    const out = buildActivity(failed);
    expect(out[0].messageKey).toBe('activity.failed');
    expect(out[0].error).toBe('rate limited');
  });
});
