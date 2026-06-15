import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const moveBookMock = vi.fn();
vi.mock('../../api', () => ({
  worldsApi: { moveBookIntoWorld: (...a: unknown[]) => moveBookMock(...a) },
}));

const createBookMock = vi.fn();
vi.mock('@/features/books/api', () => ({
  booksApi: { createBook: (...a: unknown[]) => createBookMock(...a) },
}));

import { useAddBookToWorld } from '../useAddBookToWorld';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidate };
}

beforeEach(() => {
  moveBookMock.mockReset();
  createBookMock.mockReset();
});

describe('useAddBookToWorld (W5/G1)', () => {
  it('attach(bookId) moves the book into the world and invalidates the tree + graph', async () => {
    moveBookMock.mockResolvedValue({ book_id: 'b1', world_id: 'w1' });
    const { Wrapper, invalidate } = makeWrapper();
    const { result } = renderHook(() => useAddBookToWorld('w1'), { wrapper: Wrapper });

    await act(async () => { await result.current.attach('b1'); });

    expect(moveBookMock).toHaveBeenCalledWith('tok', 'w1', 'b1');
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['living-world', 'books', 'w1'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['world-subgraph'] });
  });

  it('createAndAttach creates the book THEN attaches it (two-step, no orphan loss)', async () => {
    createBookMock.mockResolvedValue({ book_id: 'b-new', title: 'Fresh' });
    moveBookMock.mockResolvedValue({ book_id: 'b-new', world_id: 'w1' });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useAddBookToWorld('w1'), { wrapper: Wrapper });

    await act(async () => { await result.current.createAndAttach({ title: 'Fresh' }); });

    expect(createBookMock).toHaveBeenCalledWith('tok', { title: 'Fresh' });
    // attach runs AFTER create, with the new book's id.
    expect(moveBookMock).toHaveBeenCalledWith('tok', 'w1', 'b-new');
  });

  it('surfaces an attach failure after a successful create (book stays standalone)', async () => {
    createBookMock.mockResolvedValue({ book_id: 'b-new', title: 'Fresh' });
    moveBookMock.mockRejectedValue(new Error('no edit grant'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useAddBookToWorld('w1'), { wrapper: Wrapper });

    await act(async () => {
      await expect(result.current.createAndAttach({ title: 'Fresh' })).rejects.toThrow('no edit grant');
    });
    await waitFor(() => expect(result.current.error?.message).toBe('no edit grant'));
    // the book WAS created (the error is only on the attach step).
    expect(createBookMock).toHaveBeenCalledTimes(1);
  });
});
