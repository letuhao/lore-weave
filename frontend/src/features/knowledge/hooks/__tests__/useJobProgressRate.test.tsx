import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { ExtractionJobWire } from '../../api';
import {
  useJobProgressRate,
  __resetSamplesForTests,
} from '../useJobProgressRate';

function makeJob(
  overrides: Partial<ExtractionJobWire> = {},
): ExtractionJobWire {
  return {
    job_id: 'job-1',
    user_id: 'u1',
    project_id: 'p1',
    scope: 'chapters',
    scope_range: null,
    status: 'running',
    llm_model: 'claude-sonnet-4-6',
    embedding_model: 'bge-m3',
    max_spend_usd: '5.00',
    items_processed: 0,
    items_total: 100,
    cost_spent_usd: '0.00',
    current_cursor: null,
    started_at: '2026-04-19T12:00:00Z',
    paused_at: null,
    completed_at: null,
    created_at: '2026-04-19T12:00:00Z',
    updated_at: '2026-04-19T12:00:00Z',
    error_message: null,
    project_name: 'Alpha',
    ...overrides,
  };
}

describe('useJobProgressRate', () => {
  beforeEach(() => {
    __resetSamplesForTests();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-19T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns null when status !== running', () => {
    const { result } = renderHook(() =>
      useJobProgressRate(makeJob({ status: 'paused' })),
    );
    expect(result.current.minutesRemaining).toBeNull();
    expect(result.current.itemsPerSecond).toBeNull();
  });

  it('returns null when items_total is null (indeterminate)', () => {
    const { result } = renderHook(() =>
      useJobProgressRate(makeJob({ items_total: null })),
    );
    expect(result.current.minutesRemaining).toBeNull();
  });

  it('returns null on the very first sample (no rate yet)', () => {
    const { result } = renderHook(() =>
      useJobProgressRate(makeJob({ items_processed: 0 })),
    );
    expect(result.current.minutesRemaining).toBeNull();
    expect(result.current.itemsPerSecond).toBeNull();
  });

  it('computes ETA from deltas across successive renders', () => {
    // First sample at t=0: seed only.
    const { result, rerender } = renderHook(
      ({ job }: { job: ExtractionJobWire }) => useJobProgressRate(job),
      { initialProps: { job: makeJob({ items_processed: 0 }) } },
    );
    expect(result.current.minutesRemaining).toBeNull();

    // Second sample 2s later, 4 items processed — instantaneous 2 items/sec.
    vi.setSystemTime(new Date('2026-04-19T12:00:02Z'));
    rerender({ job: makeJob({ items_processed: 4 }) });

    // Remaining = 100 - 4 = 96 items at 2 items/sec = 48s = 0.8 min.
    expect(result.current.itemsPerSecond).toBeCloseTo(2, 3);
    expect(result.current.minutesRemaining).toBeCloseTo(96 / 2 / 60, 3);
  });

  it('blends via EMA — a 2x rate step converges gradually, not instantly', () => {
    const { result, rerender } = renderHook(
      ({ job }: { job: ExtractionJobWire }) => useJobProgressRate(job),
      { initialProps: { job: makeJob({ items_processed: 0 }) } },
    );

    // t=2s: 4 items → 2 items/sec (first real sample, no EMA blend yet).
    vi.setSystemTime(new Date('2026-04-19T12:00:02Z'));
    rerender({ job: makeJob({ items_processed: 4 }) });
    const rateAfterFirst = result.current.itemsPerSecond!;
    expect(rateAfterFirst).toBeCloseTo(2, 3);

    // t=4s: another 8 items → instantaneous 4 items/sec (2x jump).
    // With α=0.3: new ema = 0.3 * 4 + 0.7 * 2 = 2.6
    vi.setSystemTime(new Date('2026-04-19T12:00:04Z'));
    rerender({ job: makeJob({ items_processed: 12 }) });
    expect(result.current.itemsPerSecond).toBeCloseTo(2.6, 3);
  });

  it('resets when polling gap exceeds 60s (tab-backgrounded)', () => {
    const { result, rerender } = renderHook(
      ({ job }: { job: ExtractionJobWire }) => useJobProgressRate(job),
      { initialProps: { job: makeJob({ items_processed: 0 }) } },
    );
    vi.setSystemTime(new Date('2026-04-19T12:00:02Z'));
    rerender({ job: makeJob({ items_processed: 4 }) });
    expect(result.current.itemsPerSecond).toBeCloseTo(2, 3);

    // 90s later — treated as a fresh start, returns null for this call.
    vi.setSystemTime(new Date('2026-04-19T12:01:32Z'));
    rerender({ job: makeJob({ items_processed: 50 }) });
    expect(result.current.minutesRemaining).toBeNull();
    expect(result.current.itemsPerSecond).toBeNull();
  });
});
