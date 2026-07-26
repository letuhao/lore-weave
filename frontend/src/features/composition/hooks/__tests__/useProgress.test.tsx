import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { localDateKey, useEnsureBaseline, useReportProgress, useSetDailyGoal } from '../useProgress';

const { reportProgress, setDailyGoal, baselineProgress } = vi.hoisted(() => ({
  reportProgress: vi.fn(),
  setDailyGoal: vi.fn(),
  baselineProgress: vi.fn(),
}));
vi.mock('../../api', () => ({
  compositionApi: { reportProgress, setDailyGoal, baselineProgress, getProgress: vi.fn() },
}));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('localDateKey (T4.2)', () => {
  it('formats the LOCAL date as zero-padded YYYY-MM-DD (not UTC)', () => {
    expect(localDateKey(new Date(2026, 5, 7))).toBe('2026-06-07'); // June 7
    expect(localDateKey(new Date(2026, 11, 31))).toBe('2026-12-31');
  });
});

describe('useReportProgress (T4.2)', () => {
  beforeEach(() => { reportProgress.mockReset(); });

  it('reports the chapter snapshot for today and resolves', async () => {
    reportProgress.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useReportProgress('p1', 't'), { wrapper: makeWrapper() });
    act(() => result.current('ch1', 1234));
    await waitFor(() =>
      expect(reportProgress).toHaveBeenCalledWith(
        'p1', { chapter_id: 'ch1', words: 1234, date: localDateKey() }, 't',
      ),
    );
  });

  it('is a no-op without a projectId (pending/null-project Work)', () => {
    const { result } = renderHook(() => useReportProgress(undefined, 't'), { wrapper: makeWrapper() });
    act(() => result.current('ch1', 10));
    expect(reportProgress).not.toHaveBeenCalled();
  });

  it('swallows a failed report (never throws — advisory only)', async () => {
    reportProgress.mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useReportProgress('p1', 't'), { wrapper: makeWrapper() });
    expect(() => act(() => result.current('ch1', 5))).not.toThrow();
    await waitFor(() => expect(reportProgress).toHaveBeenCalled());
  });
});

describe('useEnsureBaseline (T4.2)', () => {
  beforeEach(() => { baselineProgress.mockReset(); });

  it('records the chapter pre-existing count (no date — insert-once server-side)', async () => {
    baselineProgress.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useEnsureBaseline('p1', 't'), { wrapper: makeWrapper() });
    act(() => result.current('ch1', 5000));
    await waitFor(() =>
      expect(baselineProgress).toHaveBeenCalledWith('p1', { chapter_id: 'ch1', words: 5000 }, 't'),
    );
  });

  it('is a no-op without a projectId', () => {
    const { result } = renderHook(() => useEnsureBaseline(undefined, 't'), { wrapper: makeWrapper() });
    act(() => result.current('ch1', 5000));
    expect(baselineProgress).not.toHaveBeenCalled();
  });

  it('swallows a failed baseline call', async () => {
    baselineProgress.mockRejectedValue(new Error('x'));
    const { result } = renderHook(() => useEnsureBaseline('p1', 't'), { wrapper: makeWrapper() });
    expect(() => act(() => result.current('ch1', 5000))).not.toThrow();
    await waitFor(() => expect(baselineProgress).toHaveBeenCalled());
  });
});

describe('useSetDailyGoal (BE-P2 — per-user goal, no shared work.settings)', () => {
  beforeEach(() => { setDailyGoal.mockReset(); setDailyGoal.mockResolvedValue({ ok: true, daily_goal: null }); });

  it('writes the goal to the caller OWN per-user route (never the shared settings blob)', async () => {
    const { result } = renderHook(() => useSetDailyGoal('b1', 't'), { wrapper: makeWrapper() });
    act(() => result.current.mutate({ projectId: 'p1', goal: 800 }));
    await waitFor(() => expect(setDailyGoal).toHaveBeenCalledWith('p1', 800, 't'));
  });

  it('clears the goal with 0', async () => {
    const { result } = renderHook(() => useSetDailyGoal('b1', 't'), { wrapper: makeWrapper() });
    act(() => result.current.mutate({ projectId: 'p1', goal: 0 }));
    await waitFor(() => expect(setDailyGoal).toHaveBeenCalledWith('p1', 0, 't'));
  });
});
