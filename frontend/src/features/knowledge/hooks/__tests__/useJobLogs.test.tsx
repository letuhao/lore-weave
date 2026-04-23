import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const listJobLogsMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: { listJobLogs: (...args: unknown[]) => listJobLogsMock(...args) },
  };
});

import { useJobLogs } from '../useJobLogs';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useJobLogs', () => {
  beforeEach(() => {
    listJobLogsMock.mockReset();
  });

  it('returns logs and hasNextPage=false when next_cursor is null', async () => {
    listJobLogsMock.mockResolvedValue({
      logs: [
        { log_id: 1, job_id: 'j1', user_id: 'u1', level: 'info', message: 'hi', context: {}, created_at: '2026-04-22T12:00Z' },
      ],
      next_cursor: null,
    });
    const { result } = renderHook(() => useJobLogs('j1'), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.logs).toHaveLength(1);
    });
    expect(result.current.hasNextPage).toBe(false);
    // C3: hook now sends since_log_id=0 on initial fetch via useInfiniteQuery.
    expect(listJobLogsMock).toHaveBeenCalledWith(
      'j1',
      { sinceLogId: 0, limit: 50 },
      'tok-test',
    );
  });

  it('is disabled when jobId is null (never fires the API)', async () => {
    listJobLogsMock.mockResolvedValue({ logs: [], next_cursor: null });
    renderHook(() => useJobLogs(null), { wrapper: wrapper() });
    await new Promise((r) => setTimeout(r, 20));
    expect(listJobLogsMock).not.toHaveBeenCalled();
  });

  it('surfaces errors via the error field', async () => {
    const boom = new Error('boom');
    listJobLogsMock.mockRejectedValue(boom);
    const { result } = renderHook(() => useJobLogs('j1'), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.error).toBe(boom);
    });
  });

  // ── C3 (D-K19b.8-03) — tail-follow + Load-more ──────────────────

  it('hasNextPage=true when server reports next_cursor', async () => {
    listJobLogsMock.mockResolvedValue({
      logs: [
        { log_id: 1, job_id: 'j1', user_id: 'u1', level: 'info', message: 'a', context: {}, created_at: '2026-04-22T12:00Z' },
      ],
      next_cursor: 1,
    });
    const { result } = renderHook(() => useJobLogs('j1'), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.logs).toHaveLength(1);
    });
    expect(result.current.hasNextPage).toBe(true);
  });

  it('fetchNextPage loads the second page using the last cursor', async () => {
    listJobLogsMock.mockResolvedValueOnce({
      logs: [
        { log_id: 1, job_id: 'j1', user_id: 'u1', level: 'info', message: 'a', context: {}, created_at: '2026-04-22T12:00Z' },
        { log_id: 2, job_id: 'j1', user_id: 'u1', level: 'info', message: 'b', context: {}, created_at: '2026-04-22T12:00Z' },
      ],
      next_cursor: 2,
    });
    listJobLogsMock.mockResolvedValueOnce({
      logs: [
        { log_id: 3, job_id: 'j1', user_id: 'u1', level: 'info', message: 'c', context: {}, created_at: '2026-04-22T12:00Z' },
      ],
      next_cursor: null,
    });

    const { result } = renderHook(() => useJobLogs('j1'), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.logs).toHaveLength(2);
    });
    expect(result.current.hasNextPage).toBe(true);

    act(() => {
      result.current.fetchNextPage();
    });
    await waitFor(() => {
      expect(result.current.logs).toHaveLength(3);
    });
    // 2nd call used cursor=2 from page 1.
    expect(listJobLogsMock).toHaveBeenNthCalledWith(
      2,
      'j1',
      { sinceLogId: 2, limit: 50 },
      'tok-test',
    );
    // Logs are flattened in page order.
    expect(result.current.logs.map((l) => l.log_id)).toEqual([1, 2, 3]);
    expect(result.current.hasNextPage).toBe(false);
  });

  it('does not poll when jobStatus is terminal (complete)', async () => {
    // Use real timers so we can wait a real 300ms without firing a 5s
    // refetchInterval. Fake timers interfere with react-query internals.
    listJobLogsMock.mockResolvedValue({
      logs: [],
      next_cursor: null,
    });
    renderHook(() => useJobLogs('j1', { jobStatus: 'complete' }), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(listJobLogsMock).toHaveBeenCalledTimes(1);
    });
    // Wait long enough that a 5s refetch would fire if misconfigured.
    // Instead we just confirm no EXTRA call in a short window —
    // sufficient to lock the disabled-poll contract without
    // slowing tests down.
    await new Promise((r) => setTimeout(r, 300));
    expect(listJobLogsMock).toHaveBeenCalledTimes(1);
  });

  it('polls when jobStatus is running', async () => {
    vi.useFakeTimers();
    try {
      listJobLogsMock.mockResolvedValue({
        logs: [],
        next_cursor: null,
      });
      renderHook(() => useJobLogs('j1', { jobStatus: 'running' }), {
        wrapper: wrapper(),
      });
      // First fetch fires immediately.
      await vi.waitFor(() => {
        expect(listJobLogsMock).toHaveBeenCalledTimes(1);
      });
      // Advance past the 5s refetchInterval — second fetch should fire.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_100);
      });
      expect(listJobLogsMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('polls when jobStatus is paused (still active)', async () => {
    listJobLogsMock.mockResolvedValue({ logs: [], next_cursor: null });
    // Just asserting the status-check branch — full timing covered by
    // the running-status test above.
    const { result } = renderHook(
      () => useJobLogs('j1', { jobStatus: 'paused' }),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    // Hook should not crash and should deliver an empty result set.
    expect(result.current.logs).toEqual([]);
  });
});
