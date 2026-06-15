import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const resolveMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: { resolveWorkProject: (...a: unknown[]) => resolveMock(...a) },
}));

import { usePendingWorkResolver } from '../useWork';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidate };
}

beforeEach(() => {
  resolveMock.mockReset();
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe('usePendingWorkResolver (D-C16 self-healing backfill poll)', () => {
  it('starts idle and resolves on the first backfill success', async () => {
    resolveMock.mockResolvedValueOnce({ project_id: 'p1', id: 'w1' });
    const { Wrapper, invalidate } = makeWrapper();
    const { result } = renderHook(() => usePendingWorkResolver('book-1', 'tok'), { wrapper: Wrapper });
    expect(result.current.state).toBe('idle');

    act(() => result.current.start('w1'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(result.current.state).toBe('idle');
    expect(resolveMock).toHaveBeenCalledWith('w1', 'tok');
    // the now-backed Work flows in via a work-query invalidation
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['composition', 'work', 'book-1'] });
  });

  it('keeps polling through STILL_PENDING (409) until it succeeds', async () => {
    resolveMock
      .mockRejectedValueOnce(new Error('409 STILL_PENDING'))
      .mockResolvedValueOnce({ project_id: 'p1' });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => usePendingWorkResolver('book-1', 'tok'), { wrapper: Wrapper });

    act(() => result.current.start('w1'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); }); // attempt 1 → 409
    expect(result.current.state).toBe('resolving');
    await act(async () => { await vi.advanceTimersByTimeAsync(600); }); // attempt 2 → success
    expect(result.current.state).toBe('idle');
    expect(resolveMock).toHaveBeenCalledTimes(2);
  });

  it('gives up to a failed state after the attempt cap', async () => {
    resolveMock.mockRejectedValue(new Error('409 STILL_PENDING'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => usePendingWorkResolver('book-1', 'tok'), { wrapper: Wrapper });

    act(() => result.current.start('w1'));
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });

    expect(result.current.state).toBe('failed');
    expect(resolveMock).toHaveBeenCalledTimes(8);
  });

  it('waits a backoff delay between attempts (not a tight 0ms loop)', async () => {
    resolveMock.mockRejectedValue(new Error('409'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => usePendingWorkResolver('book-1', 'tok'), { wrapper: Wrapper });
    act(() => result.current.start('w1'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); }); // attempt 1 at t=0
    expect(resolveMock).toHaveBeenCalledTimes(1);
    // first backoff is 500ms — advancing only 400ms must NOT fire attempt 2
    // (a fixed-0ms regression would fire it here, failing this test).
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    expect(resolveMock).toHaveBeenCalledTimes(1);
    // crossing the 500ms boundary fires attempt 2
    await act(async () => { await vi.advanceTimersByTimeAsync(150); });
    expect(resolveMock).toHaveBeenCalledTimes(2);
  });

  it('retry re-arms the same id after a give-up', async () => {
    resolveMock.mockRejectedValue(new Error('409'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => usePendingWorkResolver('book-1', 'tok'), { wrapper: Wrapper });

    act(() => result.current.start('w1'));
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(result.current.state).toBe('failed');

    resolveMock.mockReset();
    resolveMock.mockResolvedValueOnce({ project_id: 'p1' });
    act(() => result.current.retry());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.state).toBe('idle');
    expect(resolveMock).toHaveBeenCalledWith('w1', 'tok');
  });
});
