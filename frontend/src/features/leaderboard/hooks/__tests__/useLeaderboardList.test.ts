import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const apiMocks = vi.hoisted(() => ({
  listBooks: vi.fn(),
  listAuthors: vi.fn(),
  listTranslators: vi.fn(),
}));
vi.mock('../../api', () => ({ leaderboardApi: apiMocks }));

import { useLeaderboardList } from '../useLeaderboardList';

function book(overrides: Record<string, unknown> = {}) {
  return {
    rank: 1,
    book_id: 'b1',
    owner_user_id: 'u1',
    owner_display_name: 'Author',
    title: 'Title',
    genre_tags: [],
    original_language: null,
    views: 0,
    unique_readers: 0,
    chapter_count: 0,
    translation_count: 0,
    avg_rating: 0,
    rating_count: 0,
    favorites_count: 0,
    rank_change: 0,
    has_cover: false,
    ...overrides,
  };
}

function author(overrides: Record<string, unknown> = {}) {
  return {
    rank: 1,
    user_id: 'a1',
    display_name: 'Author',
    total_books: 1,
    readers: 1,
    avg_rating: 4,
    total_chapters: 1,
    ...overrides,
  };
}

function translator(overrides: Record<string, unknown> = {}) {
  return {
    rank: 1,
    user_id: 't1',
    display_name: 'Translator',
    total_chapters_done: 1,
    languages: ['en'],
    ...overrides,
  };
}

beforeEach(() => {
  apiMocks.listBooks.mockReset().mockResolvedValue({ items: [book()], total: 1, period: '30d' });
  apiMocks.listAuthors.mockReset().mockResolvedValue({ items: [author()], total: 1, period: '30d' });
  apiMocks.listTranslators.mockReset().mockResolvedValue({ items: [translator()], total: 1, period: '30d' });
});

describe('useLeaderboardList', () => {
  it('kind=books fetches books AND the author/translator previews (QuickStatsCards feed)', async () => {
    const { result } = renderHook(() => useLeaderboardList('books'));
    await waitFor(() => expect(result.current.books).toHaveLength(1));
    expect(apiMocks.listBooks).toHaveBeenCalledWith(
      expect.objectContaining({ period: '30d', sort: undefined, limit: 20, offset: 0 }),
    );
    await waitFor(() => expect(result.current.previewAuthors).toHaveLength(1));
    await waitFor(() => expect(result.current.previewTranslators).toHaveLength(1));
    expect(apiMocks.listAuthors).toHaveBeenCalledWith({ period: '30d', limit: 3 });
    expect(apiMocks.listTranslators).toHaveBeenCalledWith({ period: '30d', limit: 3 });
  });

  it('kind=authors fetches only authors — no books, no preview calls', async () => {
    const { result } = renderHook(() => useLeaderboardList('authors'));
    await waitFor(() => expect(result.current.authors).toHaveLength(1));
    expect(apiMocks.listBooks).not.toHaveBeenCalled();
    expect(apiMocks.listAuthors).toHaveBeenCalledTimes(1); // the list call only, no preview
    expect(apiMocks.listAuthors).toHaveBeenCalledWith({ period: '30d', limit: 20, offset: 0 });
    expect(apiMocks.listTranslators).not.toHaveBeenCalled();
  });

  it('kind=translators fetches only translators', async () => {
    const { result } = renderHook(() => useLeaderboardList('translators'));
    await waitFor(() => expect(result.current.translators).toHaveLength(1));
    expect(apiMocks.listBooks).not.toHaveBeenCalled();
    expect(apiMocks.listAuthors).not.toHaveBeenCalled();
    expect(apiMocks.listTranslators).toHaveBeenCalledWith({ period: '30d', limit: 20, offset: 0 });
  });

  it('kind=trending fetches books with sort forced to "trending" regardless of the local sort filter', async () => {
    const { result } = renderHook(() => useLeaderboardList('trending'));
    await waitFor(() => expect(result.current.books).toHaveLength(1));
    act(() => result.current.setSort('rating'));
    await waitFor(() =>
      expect(apiMocks.listBooks).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'trending' })),
    );
    // no preview calls for trending — only kind==='books' feeds QuickStatsCards
    expect(apiMocks.listAuthors).not.toHaveBeenCalled();
  });

  it('kind=books honors the local sort filter (not forced)', async () => {
    const { result } = renderHook(() => useLeaderboardList('books'));
    await waitFor(() => expect(result.current.books).toHaveLength(1));
    act(() => result.current.setSort('readers'));
    await waitFor(() =>
      expect(apiMocks.listBooks).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'readers' })),
    );
  });

  it('showPodium is true only once >= 3 books are loaded for books/trending', async () => {
    apiMocks.listBooks.mockResolvedValue({ items: [book({ book_id: 'b1' }), book({ book_id: 'b2' })], total: 2, period: '30d' });
    const { result } = renderHook(() => useLeaderboardList('books'));
    await waitFor(() => expect(result.current.books).toHaveLength(2));
    expect(result.current.showPodium).toBe(false);

    apiMocks.listBooks.mockResolvedValue({
      items: [book({ book_id: 'b1' }), book({ book_id: 'b2' }), book({ book_id: 'b3' })],
      total: 3,
      period: '30d',
    });
    act(() => { result.current.setGenre('Fantasy'); });
    await waitFor(() => expect(result.current.books).toHaveLength(3));
    expect(result.current.showPodium).toBe(true);
  });

  it('fetchBooks(offset, append=true) appends rather than replaces', async () => {
    const { result } = renderHook(() => useLeaderboardList('books'));
    await waitFor(() => expect(result.current.books).toHaveLength(1));
    apiMocks.listBooks.mockResolvedValueOnce({ items: [book({ book_id: 'b2' })], total: 2, period: '30d' });
    await act(async () => { await result.current.fetchBooks(1, true); });
    expect(result.current.books.map((b) => b.book_id)).toEqual(['b1', 'b2']);
  });

  it('isLoading reflects the loading flag for the active kind only', async () => {
    let resolveBooks: (v: unknown) => void = () => {};
    apiMocks.listBooks.mockReturnValueOnce(new Promise((res) => { resolveBooks = res; }));
    const { result } = renderHook(() => useLeaderboardList('books'));
    expect(result.current.isLoading).toBe(true);
    resolveBooks({ items: [], total: 0, period: '30d' });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('changing period re-fetches for the active kind', async () => {
    const { result } = renderHook(() => useLeaderboardList('authors'));
    await waitFor(() => expect(apiMocks.listAuthors).toHaveBeenCalledTimes(1));
    act(() => result.current.setPeriod('7d'));
    await waitFor(() => expect(apiMocks.listAuthors).toHaveBeenLastCalledWith({ period: '7d', limit: 20, offset: 0 }));
  });
});
