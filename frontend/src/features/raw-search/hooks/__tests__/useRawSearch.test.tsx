import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const searchMock = vi.fn();
const hybridMock = vi.fn();
vi.mock('../../api', () => ({
  rawSearchApi: {
    search: (...a: unknown[]) => searchMock(...a),
    searchHybrid: (...a: unknown[]) => hybridMock(...a),
  },
}));
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

import { useRawSearch } from '../useRawSearch';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const _hit = {
  chapterId: 'c1', chapterTitle: 'Ch', sortOrder: 1, surface: 'draft',
  matchType: 'lexical', score: 1, snippet: '乾坤圈', highlights: [[0, 3]],
  location: { blockIndex: 2, headingContext: null, charStart: 0, charEnd: 3 },
};

beforeEach(() => {
  searchMock.mockReset();
  hybridMock.mockReset();
  searchMock.mockResolvedValue({ query: '', mode: 'lexical', results: [] });
  hybridMock.mockResolvedValue({ query: '', mode: 'hybrid', results: [] });
});

describe('useRawSearch', () => {
  it('is disabled and calls neither leg for a blank query', async () => {
    const { result } = renderHook(() => useRawSearch('book-1', '   '), { wrapper });
    expect(result.current.disabled).toBe(true);
    await Promise.resolve();
    expect(searchMock).not.toHaveBeenCalled();
    expect(hybridMock).not.toHaveBeenCalled();
  });

  it('defaults to the HYBRID leg and returns hits + degraded', async () => {
    hybridMock.mockResolvedValue({
      query: '乾坤圈', mode: 'hybrid', results: [_hit],
      degraded: { semantic: 'embed_unavailable' },
    });
    const { result } = renderHook(() => useRawSearch('book-1', '乾坤圈'), { wrapper });
    await waitFor(() => expect(result.current.hits).toHaveLength(1));
    expect(hybridMock).toHaveBeenCalledWith(
      'book-1',
      { q: '乾坤圈', mode: 'hybrid', limit: 20, granularity: 'chapter', rerank: true },
      'tok',
    );
    expect(searchMock).not.toHaveBeenCalled();
    expect(result.current.degraded).toEqual({ semantic: 'embed_unavailable' });
  });

  it('mode "lexical" calls the book-service leg directly', async () => {
    searchMock.mockResolvedValue({ query: 'x', mode: 'lexical', results: [_hit] });
    const { result } = renderHook(
      () => useRawSearch('book-1', 'x', { mode: 'lexical' }), { wrapper },
    );
    await waitFor(() => expect(result.current.hits).toHaveLength(1));
    expect(searchMock).toHaveBeenCalledWith(
      'book-1', { q: 'x', limit: 20, granularity: 'chapter' }, 'tok',
    );
    expect(hybridMock).not.toHaveBeenCalled();
  });
});
