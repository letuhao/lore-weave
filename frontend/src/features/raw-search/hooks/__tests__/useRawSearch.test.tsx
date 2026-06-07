import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const searchMock = vi.fn();
vi.mock('../../api', () => ({
  rawSearchApi: { search: (...a: unknown[]) => searchMock(...a) },
}));
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

import { useRawSearch } from '../useRawSearch';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  searchMock.mockReset();
  searchMock.mockResolvedValue({ query: '', mode: 'lexical', results: [] });
});

describe('useRawSearch', () => {
  it('is disabled and does not call the API for a blank query', async () => {
    const { result } = renderHook(() => useRawSearch('book-1', '   '), { wrapper });
    expect(result.current.disabled).toBe(true);
    await Promise.resolve();
    expect(searchMock).not.toHaveBeenCalled();
  });

  it('searches when a query is present and returns hits', async () => {
    const hit = {
      chapterId: 'c1', chapterTitle: 'Ch', sortOrder: 1,
      surface: 'draft', matchType: 'lexical', score: 1,
      snippet: '乾坤圈', highlights: [[0, 3]],
      location: { blockIndex: 2, headingContext: null, charStart: 0, charEnd: 3 },
    };
    searchMock.mockResolvedValue({ query: '乾坤圈', mode: 'lexical', results: [hit] });
    const { result } = renderHook(() => useRawSearch('book-1', '乾坤圈'), { wrapper });
    await waitFor(() => expect(result.current.hits).toHaveLength(1));
    expect(result.current.disabled).toBe(false);
    expect(searchMock).toHaveBeenCalledWith('book-1', { q: '乾坤圈', limit: 20 }, 'tok');
  });
});
