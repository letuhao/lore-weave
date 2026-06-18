import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const getBookMock = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { getBook: (...a: unknown[]) => getBookMock(...a) },
}));
const getWorldMock = vi.fn();
vi.mock('@/features/world/api', () => ({
  worldsApi: { getWorld: (...a: unknown[]) => getWorldMock(...a) },
}));

import { useProjectBacklinks } from '../useProjectBacklinks';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  getBookMock.mockReset();
  getWorldMock.mockReset();
});

describe('useProjectBacklinks (D-WORLD-PROJECT-BACKLINK)', () => {
  it('resolves the book title and, when grouped, the world name', async () => {
    getBookMock.mockResolvedValue({ book_id: 'b1', title: 'Cradle', world_id: 'w1' });
    getWorldMock.mockResolvedValue({ world_id: 'w1', name: 'Aethyr' });
    const { result } = renderHook(() => useProjectBacklinks('b1'), { wrapper });
    await waitFor(() => expect(result.current.bookTitle).toBe('Cradle'));
    await waitFor(() => expect(result.current.worldName).toBe('Aethyr'));
    expect(result.current.worldId).toBe('w1');
    expect(getBookMock).toHaveBeenCalledWith('tok', 'b1');
    expect(getWorldMock).toHaveBeenCalledWith('tok', 'w1');
  });

  it('does not fetch a world when the book is standalone', async () => {
    getBookMock.mockResolvedValue({ book_id: 'b1', title: 'Standalone', world_id: null });
    const { result } = renderHook(() => useProjectBacklinks('b1'), { wrapper });
    await waitFor(() => expect(result.current.bookTitle).toBe('Standalone'));
    expect(result.current.worldId).toBeNull();
    expect(getWorldMock).not.toHaveBeenCalled();
  });

  it('does not fetch anything when the project has no book', async () => {
    const { result } = renderHook(() => useProjectBacklinks(null), { wrapper });
    expect(result.current.bookTitle).toBeNull();
    expect(getBookMock).not.toHaveBeenCalled();
  });
});
