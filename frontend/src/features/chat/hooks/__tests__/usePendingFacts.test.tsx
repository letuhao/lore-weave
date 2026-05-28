import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import type { PendingFact } from '../../types';

// K21-C (D8): usePendingFacts — list query + confirm/reject mutations.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const listMock = vi.fn();
const confirmMock = vi.fn();
const rejectMock = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    listPendingFacts: (...a: unknown[]) => listMock(...a),
    confirmPendingFact: (...a: unknown[]) => confirmMock(...a),
    rejectPendingFact: (...a: unknown[]) => rejectMock(...a),
  },
}));

import { usePendingFacts } from '../usePendingFacts';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const FACT: PendingFact = {
  pending_fact_id: 'pf-1',
  user_id: 'u-1',
  project_id: 'proj-1',
  session_id: 's-1',
  fact_type: 'preference',
  fact_text: 'The user prefers tea.',
  created_at: '2026-05-17T00:00:00Z',
};

describe('usePendingFacts', () => {
  beforeEach(() => {
    listMock.mockReset();
    confirmMock.mockReset();
    rejectMock.mockReset();
  });

  it('lists pending facts for the session', async () => {
    listMock.mockResolvedValue([FACT]);
    const { result } = renderHook(() => usePendingFacts('s-1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pendingFacts).toEqual([FACT]));
    expect(listMock).toHaveBeenCalledWith('tok-test', 's-1');
  });

  it('does not query when sessionId is null', async () => {
    listMock.mockResolvedValue([FACT]);
    const { result } = renderHook(() => usePendingFacts(null), { wrapper: wrapper() });
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.pendingFacts).toEqual([]);
    expect(listMock).not.toHaveBeenCalled();
  });

  it('confirm calls the API then refetches the list', async () => {
    listMock.mockResolvedValueOnce([FACT]).mockResolvedValueOnce([]);
    confirmMock.mockResolvedValue({ id: 'fact-1' });
    const { result } = renderHook(() => usePendingFacts('s-1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pendingFacts).toEqual([FACT]));

    await act(async () => {
      await result.current.confirm('pf-1');
    });
    expect(confirmMock).toHaveBeenCalledWith('tok-test', 'pf-1');
    await waitFor(() => expect(result.current.pendingFacts).toEqual([]));
  });

  it('reject calls the API then refetches the list', async () => {
    listMock.mockResolvedValueOnce([FACT]).mockResolvedValueOnce([]);
    rejectMock.mockResolvedValue(undefined);
    const { result } = renderHook(() => usePendingFacts('s-1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pendingFacts).toEqual([FACT]));

    await act(async () => {
      await result.current.reject('pf-1');
    });
    expect(rejectMock).toHaveBeenCalledWith('tok-test', 'pf-1');
    await waitFor(() => expect(result.current.pendingFacts).toEqual([]));
  });

  it('refetch re-runs the list query', async () => {
    listMock.mockResolvedValue([FACT]);
    const { result } = renderHook(() => usePendingFacts('s-1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pendingFacts).toEqual([FACT]));
    expect(listMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      result.current.refetch();
    });
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
  });

  it('surfaces a list error', async () => {
    const boom = new Error('list failed');
    listMock.mockRejectedValue(boom);
    const { result } = renderHook(() => usePendingFacts('s-1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.error).toBe(boom));
  });

  it('propagates a confirm rejection to the caller', async () => {
    listMock.mockResolvedValue([FACT]);
    confirmMock.mockRejectedValue(new Error('confirm failed'));
    const { result } = renderHook(() => usePendingFacts('s-1'), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.pendingFacts).toEqual([FACT]));

    await expect(
      act(async () => {
        await result.current.confirm('pf-1');
      }),
    ).rejects.toThrow('confirm failed');
  });
});
