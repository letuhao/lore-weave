import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const listEntitiesMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      listEntities: (...args: unknown[]) => listEntitiesMock(...args),
    },
  };
});

import { useEntities } from '../useEntities';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('useEntities', () => {
  beforeEach(() => {
    listEntitiesMock.mockReset();
    useAuthMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok-test',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('passes filter + pagination params through to the API and surfaces total', async () => {
    listEntitiesMock.mockResolvedValue({
      entities: [
        {
          id: 'ent-1',
          user_id: 'u1',
          project_id: 'p-1',
          name: 'Kai',
          canonical_name: 'kai',
          kind: 'character',
          aliases: ['Kai'],
          canonical_version: 1,
          source_types: ['chapter'],
          confidence: 0.9,
          archived_at: null,
          archive_reason: null,
          evidence_count: 5,
          mention_count: 12,
          created_at: null,
          updated_at: null,
        },
      ],
      total: 42,
    });
    const params = {
      project_id: 'p-1',
      kind: 'character',
      search: 'kai',
      limit: 25,
      offset: 50,
    };
    const { result } = renderHook(() => useEntities(params), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.entities).toHaveLength(1);
    });
    expect(result.current.total).toBe(42);
    expect(listEntitiesMock).toHaveBeenCalledWith(params, 'tok-test');
  });

  it('returns empty list + total 0 while loading, then resolves', async () => {
    listEntitiesMock.mockResolvedValue({ entities: [], total: 0 });
    const { result } = renderHook(() => useEntities({}), {
      wrapper: wrapper(),
    });
    expect(result.current.entities).toEqual([]);
    expect(result.current.total).toBe(0);
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.total).toBe(0);
  });

  it('surfaces API errors via the error field', async () => {
    const boom = new Error('listing failed');
    listEntitiesMock.mockRejectedValue(boom);
    const { result } = renderHook(() => useEntities({}), {
      wrapper: wrapper(),
    });
    await waitFor(() => {
      expect(result.current.error).toBe(boom);
    });
  });

  it('scopes queryKey by userId so logout→login cannot leak cache (review-impl M1)', async () => {
    // Two separate QueryClients with two different authed users.
    // If userId weren't in the key, both would hit the same cache
    // entry. We assert the API is called once PER user_id.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrap = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    listEntitiesMock.mockResolvedValue({ entities: [], total: 0 });

    useAuthMock.mockReturnValue({
      accessToken: 'tok-a',
      user: { user_id: 'user-A', email: 'a@b', display_name: null, avatar_url: null },
    });
    const { result: r1, unmount } = renderHook(() => useEntities({}), {
      wrapper: wrap,
    });
    await waitFor(() => {
      expect(r1.current.isLoading).toBe(false);
    });
    unmount();

    useAuthMock.mockReturnValue({
      accessToken: 'tok-b',
      user: { user_id: 'user-B', email: 'c@d', display_name: null, avatar_url: null },
    });
    const { result: r2 } = renderHook(() => useEntities({}), { wrapper: wrap });
    await waitFor(() => {
      expect(r2.current.isLoading).toBe(false);
    });

    // Two distinct userIds → two distinct cache entries → two BE calls.
    expect(listEntitiesMock).toHaveBeenCalledTimes(2);
  });
});
