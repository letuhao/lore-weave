import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const searchDrawersMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      searchDrawers: (...args: unknown[]) => searchDrawersMock(...args),
    },
  };
});

import { useDrawerSearch } from '../useDrawerSearch';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const HIT_STUB = {
  id: 'pg-1',
  project_id: 'p-1',
  source_type: 'chapter',
  source_id: 'ch-12',
  chunk_index: 0,
  text: 'The duel at the bridge.',
  is_hub: false,
  chapter_index: 12,
  created_at: null,
  raw_score: 0.87,
};

describe('useDrawerSearch', () => {
  beforeEach(() => {
    searchDrawersMock.mockReset();
    useAuthMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok-test',
      user: {
        user_id: 'u1',
        email: 'a@b',
        display_name: null,
        avatar_url: null,
      },
    });
  });

  it('is disabled until projectId AND query>=3 chars are provided', async () => {
    searchDrawersMock.mockResolvedValue({
      hits: [HIT_STUB],
      embedding_model: 'bge-m3',
    });
    // Missing projectId.
    const { result: r1, rerender } = renderHook(
      ({ project_id, query }) => useDrawerSearch({ project_id, query }),
      {
        wrapper: wrapper(),
        initialProps: { project_id: '', query: 'longer than three' },
      },
    );
    expect(r1.current.disabled).toBe(true);
    // Short query (<3 chars).
    rerender({ project_id: 'p-1', query: 'ab' });
    expect(r1.current.disabled).toBe(true);
    // Valid projectId + long-enough query.
    rerender({ project_id: 'p-1', query: 'bridge' });
    await waitFor(() => {
      expect(searchDrawersMock).toHaveBeenCalled();
    });
    // At most ONE BE call — the two disabled renders above must not
    // have fired searchDrawers.
    expect(searchDrawersMock).toHaveBeenCalledTimes(1);
    expect(searchDrawersMock).toHaveBeenCalledWith(
      { project_id: 'p-1', query: 'bridge' },
      'tok-test',
    );
  });

  it('surfaces hits + embedding_model on happy path', async () => {
    searchDrawersMock.mockResolvedValue({
      hits: [HIT_STUB],
      embedding_model: 'bge-m3',
    });
    const { result } = renderHook(
      () =>
        useDrawerSearch({ project_id: 'p-1', query: 'bridge', limit: 25 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.hits).toHaveLength(1);
    });
    expect(result.current.embeddingModel).toBe('bge-m3');
    expect(result.current.disabled).toBe(false);
    expect(searchDrawersMock).toHaveBeenCalledWith(
      { project_id: 'p-1', query: 'bridge', limit: 25 },
      'tok-test',
    );
  });

  it('scopes queryKey by userId so logout→login cannot leak cache (M1)', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrap = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    searchDrawersMock.mockResolvedValue({
      hits: [],
      embedding_model: 'bge-m3',
    });

    useAuthMock.mockReturnValue({
      accessToken: 'tok-a',
      user: {
        user_id: 'user-A',
        email: 'a@b',
        display_name: null,
        avatar_url: null,
      },
    });
    const { result: r1, unmount } = renderHook(
      () => useDrawerSearch({ project_id: 'p-1', query: 'bridge' }),
      { wrapper: wrap },
    );
    await waitFor(() => expect(r1.current.isLoading).toBe(false));
    unmount();

    useAuthMock.mockReturnValue({
      accessToken: 'tok-b',
      user: {
        user_id: 'user-B',
        email: 'c@d',
        display_name: null,
        avatar_url: null,
      },
    });
    const { result: r2 } = renderHook(
      () => useDrawerSearch({ project_id: 'p-1', query: 'bridge' }),
      { wrapper: wrap },
    );
    await waitFor(() => expect(r2.current.isLoading).toBe(false));

    expect(searchDrawersMock).toHaveBeenCalledTimes(2);
  });
});
