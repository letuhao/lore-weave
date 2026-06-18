import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const getWorldTimelineMock = vi.fn();
vi.mock('@/features/knowledge/api', () => ({
  knowledgeApi: { getWorldTimeline: (...a: unknown[]) => getWorldTimelineMock(...a) },
}));

import { useWorldTimeline } from '../useWorldTimeline';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => getWorldTimelineMock.mockReset());

describe('useWorldTimeline (D-WORLD-TIMELINE-ROLLUP)', () => {
  it('fetches the rollup and counts distinct source books', async () => {
    getWorldTimelineMock.mockResolvedValue({
      events: [
        { id: 'a', project_id: 'p1', title: 'A', event_order: 1 },
        { id: 'b', project_id: 'p1', title: 'B', event_order: 2 },
        { id: 'c', project_id: 'p2', title: 'C', event_order: 3 },
      ],
      total: 3,
      truncated: false,
    });
    const { result } = renderHook(() => useWorldTimeline('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(getWorldTimelineMock).toHaveBeenCalledWith('w1', { sort_by: 'narrative', limit: 100 }, 'tok');
    expect(result.current.events).toHaveLength(3);
    expect(result.current.sourceCount).toBe(2);
    expect(result.current.truncated).toBe(false);
  });

  it('surfaces truncated', async () => {
    getWorldTimelineMock.mockResolvedValue({ events: [], total: 0, truncated: true });
    const { result } = renderHook(() => useWorldTimeline('w1'), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.truncated).toBe(true);
  });

  it('does not fetch when worldId is undefined', () => {
    const { result } = renderHook(() => useWorldTimeline(undefined), { wrapper });
    expect(result.current.events).toEqual([]);
    expect(getWorldTimelineMock).not.toHaveBeenCalled();
  });
});
