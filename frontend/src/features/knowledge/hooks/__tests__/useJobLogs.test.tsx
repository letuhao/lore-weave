import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
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

  it('returns logs and next_cursor from the API', async () => {
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
    expect(result.current.nextCursor).toBeNull();
    expect(listJobLogsMock).toHaveBeenCalledWith('j1', { limit: 50 }, 'tok-test');
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
});
