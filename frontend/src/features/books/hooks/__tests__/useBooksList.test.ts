import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { Book } from '../../api';

// 14_utility_panels.md Phase C1 — useBooksList extraction. Mirrors the useGlossaryEntity test
// shape: hoisted API mocks, mountHook helper, assert both the fetch/create LOGIC (this hook's
// whole reason for existing) and the pure hashToHue helper both consumers share.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const apiMocks = vi.hoisted(() => ({
  listBooks: vi.fn(),
  createBook: vi.fn(),
}));
vi.mock('@/features/books/api', () => ({ booksApi: apiMocks }));

const translationMocks = vi.hoisted(() => ({
  getBookCoverage: vi.fn(),
}));
vi.mock('@/features/translation/api', () => ({ translationApi: translationMocks }));

import { useBooksList, hashToHue } from '../useBooksList';

function book(overrides: Partial<Book> = {}): Book {
  return {
    book_id: 'b1',
    owner_user_id: 'u1',
    title: 'Fengshen Yanyi',
    original_language: 'zh',
    chapter_count: 12,
    genre_tags: ['xianxia'],
    lifecycle_state: 'active',
    ...overrides,
  };
}

async function mountHook() {
  const { result } = renderHook(() => useBooksList());
  await waitFor(() => expect(result.current.loading).toBe(false));
  return result;
}

beforeEach(() => {
  apiMocks.listBooks.mockReset();
  apiMocks.createBook.mockReset();
  translationMocks.getBookCoverage.mockReset();
  apiMocks.listBooks.mockResolvedValue({ items: [book()], total: 1 });
  translationMocks.getBookCoverage.mockResolvedValue({ known_languages: [] });
});

describe('useBooksList', () => {
  it('loads books on mount', async () => {
    const result = await mountHook();
    expect(apiMocks.listBooks).toHaveBeenCalledWith('tok');
    expect(result.current.filteredBooks).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('filters by title search (case-insensitive)', async () => {
    apiMocks.listBooks.mockResolvedValue({
      items: [book({ book_id: 'b1', title: 'Fengshen Yanyi' }), book({ book_id: 'b2', title: 'Journey West' })],
      total: 2,
    });
    const result = await mountHook();
    act(() => result.current.setSearch('journey'));
    expect(result.current.filteredBooks.map((b) => b.book_id)).toEqual(['b2']);
  });

  it('filters by language', async () => {
    apiMocks.listBooks.mockResolvedValue({
      items: [book({ book_id: 'b1', original_language: 'zh' }), book({ book_id: 'b2', original_language: 'en' })],
      total: 2,
    });
    const result = await mountHook();
    act(() => result.current.setLangFilter('en'));
    expect(result.current.filteredBooks.map((b) => b.book_id)).toEqual(['b2']);
  });

  it('derives allLanguages from the loaded books, deduped', async () => {
    apiMocks.listBooks.mockResolvedValue({
      items: [
        book({ book_id: 'b1', original_language: 'zh' }),
        book({ book_id: 'b2', original_language: 'zh' }),
        book({ book_id: 'b3', original_language: 'en' }),
      ],
      total: 3,
    });
    const result = await mountHook();
    expect(result.current.allLanguages.sort()).toEqual(['en', 'zh']);
  });

  it('fetches translation coverage per book and populates bookLangs', async () => {
    translationMocks.getBookCoverage.mockResolvedValue({ known_languages: ['en', 'vi'] });
    const result = await mountHook();
    await waitFor(() => expect(result.current.bookLangs['b1']).toEqual(['en', 'vi']));
    expect(translationMocks.getBookCoverage).toHaveBeenCalledWith('tok', 'b1');
  });

  it('handleCreate: creates the book, resets the form, closes the dialog, and reloads', async () => {
    apiMocks.createBook.mockResolvedValue(book({ book_id: 'b2', title: 'New Book' }));
    const result = await mountHook();
    act(() => {
      result.current.setNewTitle('New Book');
      result.current.setNewLang('en'); // F16 — language is required
      result.current.setCreateOpen(true);
    });
    let created: string | undefined;
    await act(async () => { created = await result.current.handleCreate(); });
    expect(apiMocks.createBook).toHaveBeenCalledWith('tok', {
      title: 'New Book',
      description: undefined,
      original_language: 'en',
    });
    expect(result.current.createOpen).toBe(false);
    expect(result.current.newTitle).toBe('');
    // reload() re-fetched — listBooks called once for mount + once for post-create reload
    expect(apiMocks.listBooks).toHaveBeenCalledTimes(2);
    // D-BOOKS-CREATE-TO-STUDIO: the new book_id is returned so a caller
    // (BooksPage) can navigate straight into its Studio.
    expect(created).toBe('b2');
  });

  it('handleCreate is a no-op with a blank title (no API call, returns undefined)', async () => {
    const result = await mountHook();
    let created: string | undefined;
    await act(async () => { created = await result.current.handleCreate(); });
    expect(apiMocks.createBook).not.toHaveBeenCalled();
    expect(created).toBeUndefined();
  });

  it('F16 — handleCreate is a no-op with a title but NO language (no language-less book)', async () => {
    const result = await mountHook();
    act(() => { result.current.setNewTitle('Has Title'); }); // but newLang stays ''
    let created: string | undefined;
    await act(async () => { created = await result.current.handleCreate(); });
    expect(apiMocks.createBook).not.toHaveBeenCalled();
    expect(created).toBeUndefined();
  });

  it('handleCreate surfaces a failure via error without closing the dialog, returns undefined', async () => {
    apiMocks.createBook.mockRejectedValue(new Error('title already exists'));
    const result = await mountHook();
    act(() => {
      result.current.setNewTitle('Dup');
      result.current.setNewLang('en'); // F16 — language is required
      result.current.setCreateOpen(true);
    });
    let created: string | undefined;
    await act(async () => { created = await result.current.handleCreate(); });
    expect(result.current.error).toBe('title already exists');
    expect(result.current.createOpen).toBe(true);
    expect(created).toBeUndefined();
  });
});

describe('hashToHue', () => {
  it('is deterministic for the same id', () => {
    expect(hashToHue('book-123')).toBe(hashToHue('book-123'));
  });

  it('stays within a valid hue range [0, 360)', () => {
    for (const id of ['a', 'book-1', 'zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz']) {
      const hue = hashToHue(id);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    }
  });
});
