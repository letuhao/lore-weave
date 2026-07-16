// 3a-B — the 6-tab partition guard. spec 33 §3.1: ONE GET /motifs/book/{id} response feeds
// BOTH the Book and Shared tabs, partitioned client-side — "a reviewer who finds an
// un-book_id-filtered Book tab has found a defect." This test locks that partition:
//   • Book   = row.book_id === bookId && !row.book_shared   (this book's private labels only —
//              NEVER the caller's globals, which are already on Mine)
//   • Shared = row.book_shared === true
// and asserts the book endpoint is fetched ONCE (not twice).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useMotifLibrary } from '../hooks/useMotifLibrary';
import { motifApi } from '../api';

vi.mock('../api', () => ({
  motifApi: { list: vi.fn(), catalog: vi.fn(), book: vi.fn() },
}));

const BOOK = 'book-1';
const rows = [
  { id: 'g1', book_id: null, book_shared: false, code: 'glob', name: 'A global (Mine tier)', kind: 'scheme', genre_tags: [], owner_user_id: 'u', visibility: 'private' },
  { id: 'b1', book_id: BOOK, book_shared: false, code: 'priv', name: 'This book label', kind: 'scheme', genre_tags: [], owner_user_id: 'u', visibility: 'private' },
  { id: 's1', book_id: BOOK, book_shared: true, code: 'shar', name: 'Shared tier', kind: 'scheme', genre_tags: [], owner_user_id: 'u', visibility: 'private' },
];

function wrapper() {
  // staleTime Infinity: re-observing the same key (book→shared tab switch) must NOT refetch —
  // that is exactly the "one fetch feeds both tabs" contract we assert below.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity } } });
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  (motifApi.book as ReturnType<typeof vi.fn>).mockResolvedValue({ motifs: rows });
});

describe('useMotifLibrary — 6-tab partition', () => {
  it('Book tab shows ONLY this book\'s private labels (not globals, not shared)', async () => {
    const { result } = renderHook(() => useMotifLibrary('t', { initialScope: 'book', bookId: BOOK }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.motifs.length).toBe(1));
    expect(result.current.motifs.map((m) => m.id)).toEqual(['b1']);   // not g1 (global), not s1 (shared)
  });

  it('Shared tab shows ONLY book_shared rows', async () => {
    const { result } = renderHook(() => useMotifLibrary('t', { initialScope: 'shared', bookId: BOOK }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.motifs.length).toBe(1));
    expect(result.current.motifs.map((m) => m.id)).toEqual(['s1']);
  });

  it('feeds a tab from a SINGLE book fetch — no double query (§3.1 "do NOT call it twice")', async () => {
    // The Book and Shared tabs share ONE bookQuery (one key, partitioned in-memory). A design
    // that fetched the endpoint per-tab would call book() more than once for one rendered tab.
    const { result } = renderHook(() => useMotifLibrary('t', { initialScope: 'shared', bookId: BOOK }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.motifs.map((m) => m.id)).toEqual(['s1']));
    expect(motifApi.book).toHaveBeenCalledTimes(1);
    expect(motifApi.book).toHaveBeenCalledWith(BOOK, 't', expect.anything());
  });

  it('book/shared queries are disabled without a bookId (no 422 fetch)', async () => {
    const { result } = renderHook(() => useMotifLibrary('t', { initialScope: 'book', bookId: null }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.hasBook).toBe(false));
    expect(motifApi.book).not.toHaveBeenCalled();
    expect(result.current.motifs).toEqual([]);
  });

  it('System tab calls list with scope=system', async () => {
    (motifApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({ motifs: [rows[0]] });
    const { result } = renderHook(() => useMotifLibrary('t', { initialScope: 'system', bookId: BOOK }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.motifs.length).toBe(1));
    expect(motifApi.list).toHaveBeenCalledWith(expect.objectContaining({ scope: 'system' }), 't');
  });
});

describe('useMotifLibrary — offset pagination (§2#9 scale)', () => {
  it('a full page ⇒ hasMore; loadMore fetches the next offset and accumulates', async () => {
    const page1 = Array.from({ length: 100 }, (_, i) => ({ id: `m${i}`, book_id: null, book_shared: false, code: `c${i}`, name: `M${i}`, kind: 'scheme', genre_tags: [], owner_user_id: 'u', visibility: 'private' }));
    const page2 = [{ id: 'm100', book_id: null, book_shared: false, code: 'c100', name: 'M100', kind: 'scheme', genre_tags: [], owner_user_id: 'u', visibility: 'private' }];
    (motifApi.list as ReturnType<typeof vi.fn>).mockImplementation((p: { offset?: number }) =>
      Promise.resolve({ motifs: (p.offset ?? 0) === 0 ? page1 : page2 }));
    const { result } = renderHook(() => useMotifLibrary('t', { initialScope: 'my', bookId: null }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.motifs.length).toBe(100));
    expect(result.current.hasMore).toBe(true);   // a full page ⇒ maybe more
    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.motifs.length).toBe(101));   // accumulated
    expect(result.current.hasMore).toBe(false);   // short page ⇒ done
    expect(motifApi.list).toHaveBeenCalledWith(expect.objectContaining({ offset: 100 }), 't');
  });

  it('a short first page ⇒ no hasMore (no load-more button)', async () => {
    (motifApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({ motifs: [{ id: 'm1', book_id: null, book_shared: false, code: 'c', name: 'M', kind: 'scheme', genre_tags: [], owner_user_id: 'u', visibility: 'private' }] });
    const { result } = renderHook(() => useMotifLibrary('t', { initialScope: 'my', bookId: null }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.motifs.length).toBe(1));
    expect(result.current.hasMore).toBe(false);
  });
});
