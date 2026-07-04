import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { Book, Chapter } from '../../api';

// 14_utility_panels.md Phase C3 — useBookReaderContent extraction. Router-free: bookId/
// chapterId are passed as ARGS (never useParams()), so this hook can be driven by BOTH
// ReaderPage's route params AND the book-reader dock panel's props.params.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const booksApiMocks = vi.hoisted(() => ({
  getBook: vi.fn(),
  getDraft: vi.fn(),
  listChapters: vi.fn(),
  getReadingProgress: vi.fn(),
}));
vi.mock('@/features/books/api', () => ({ booksApi: booksApiMocks }));

const versionsApiMocks = vi.hoisted(() => ({
  listChapterVersions: vi.fn(),
  getChapterVersion: vi.fn(),
}));
vi.mock('@/features/translation/api', () => ({ versionsApi: versionsApiMocks }));

import { useBookReaderContent, computeReadingStats } from '../useBookReaderContent';

const BOOK_ID = 'book-1';
const CHAPTER_ID = 'ch-1';

function book(overrides: Partial<Book> = {}): Book {
  return {
    book_id: BOOK_ID,
    owner_user_id: 'u1',
    title: 'Fengshen Yanyi',
    original_language: 'zh',
    chapter_count: 2,
    genre_tags: [],
    lifecycle_state: 'active',
    ...overrides,
  };
}

function chapter(overrides: Partial<Chapter> = {}): Chapter {
  return {
    chapter_id: CHAPTER_ID,
    book_id: BOOK_ID,
    title: 'Chapter One',
    original_filename: 'ch1.txt',
    original_language: 'zh',
    content_type: 'text/plain',
    byte_size: 100,
    sort_order: 1,
    lifecycle_state: 'active',
    ...overrides,
  };
}

async function mountHook(bookId = BOOK_ID, chapterId = CHAPTER_ID) {
  const { result } = renderHook(() => useBookReaderContent(bookId, chapterId));
  await waitFor(() => expect(result.current.loading).toBe(false));
  return result;
}

beforeEach(() => {
  Object.values(booksApiMocks).forEach((m) => m.mockReset());
  Object.values(versionsApiMocks).forEach((m) => m.mockReset());
  booksApiMocks.getBook.mockResolvedValue(book());
  booksApiMocks.getDraft.mockResolvedValue({
    chapter_id: CHAPTER_ID,
    body: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Hello world' }] }] },
    draft_format: 'json',
    draft_updated_at: '2026-07-04T00:00:00Z',
    draft_version: 1,
    text_content: 'Hello world',
  });
  booksApiMocks.listChapters.mockResolvedValue({ items: [chapter(), chapter({ chapter_id: 'ch-2', sort_order: 2 })], total: 2 });
  booksApiMocks.getReadingProgress.mockResolvedValue({ items: [] });
  versionsApiMocks.listChapterVersions.mockResolvedValue({ languages: [] });
});

describe('useBookReaderContent', () => {
  it('does nothing until both bookId and chapterId are non-empty (panel bootstrap case)', () => {
    const { result } = renderHook(() => useBookReaderContent(BOOK_ID, ''));
    expect(result.current.loading).toBe(true);
    expect(booksApiMocks.getBook).not.toHaveBeenCalled();
  });

  it('loads book/chapters/blocks/reading-progress for a (bookId, chapterId) pair', async () => {
    const result = await mountHook();
    expect(booksApiMocks.getBook).toHaveBeenCalledWith('tok', BOOK_ID);
    expect(booksApiMocks.getDraft).toHaveBeenCalledWith('tok', BOOK_ID, CHAPTER_ID);
    expect(result.current.book?.book_id).toBe(BOOK_ID);
    expect(result.current.chapter?.chapter_id).toBe(CHAPTER_ID);
    expect(result.current.blocks).toHaveLength(1);
    expect(result.current.originalBlocks).toEqual(result.current.blocks);
  });

  it('derives currentIdx/prevCh/nextCh/progress from the chapter list', async () => {
    const result = await mountHook();
    expect(result.current.currentIdx).toBe(0);
    expect(result.current.prevCh).toBeNull();
    expect(result.current.nextCh?.chapter_id).toBe('ch-2');
    expect(result.current.progress).toBe(50);
  });

  it('builds the original-language option plus any translated-version languages', async () => {
    versionsApiMocks.listChapterVersions.mockResolvedValue({
      languages: [{ target_language: 'en', active_id: 'v1' }],
    });
    const result = await mountHook();
    expect(result.current.languages).toEqual([
      { code: 'zh', isOriginal: true },
      { code: 'en', isOriginal: false },
    ]);
    expect(result.current.langVersionMap).toEqual({ en: 'v1' });
    expect(result.current.activeLanguage).toBe('zh');
  });

  it('handleLanguageChange switches back to original blocks with no API call', async () => {
    const result = await mountHook();
    await act(async () => { await result.current.handleLanguageChange('zh'); });
    expect(result.current.activeLanguage).toBe('zh');
    expect(versionsApiMocks.getChapterVersion).not.toHaveBeenCalled();
  });

  it('handleLanguageChange fetches and renders a JSON-format translated version', async () => {
    versionsApiMocks.listChapterVersions.mockResolvedValue({
      languages: [{ target_language: 'en', active_id: 'v1' }],
    });
    versionsApiMocks.getChapterVersion.mockResolvedValue({
      translated_body_format: 'json',
      translated_body_json: [{ type: 'paragraph', content: [{ type: 'text', text: 'Hi' }] }],
      translated_body: null,
    });
    const result = await mountHook();
    await act(async () => { await result.current.handleLanguageChange('en'); });
    expect(result.current.activeLanguage).toBe('en');
    expect(result.current.blocks).toEqual([{ type: 'paragraph', content: [{ type: 'text', text: 'Hi' }] }]);
  });

  it('handleLanguageChange falls back to legacy text→paragraph-block conversion', async () => {
    versionsApiMocks.listChapterVersions.mockResolvedValue({
      languages: [{ target_language: 'en', active_id: 'v1' }],
    });
    versionsApiMocks.getChapterVersion.mockResolvedValue({
      translated_body_format: 'text',
      translated_body_json: null,
      translated_body: 'Para one\n\nPara two',
    });
    const result = await mountHook();
    await act(async () => { await result.current.handleLanguageChange('en'); });
    expect(result.current.blocks).toHaveLength(2);
    expect(result.current.blocks[0].content?.[0]).toEqual({ type: 'text', text: 'Para one' });
  });

  it('handleLanguageChange reverts to the original on a fetch failure', async () => {
    versionsApiMocks.listChapterVersions.mockResolvedValue({
      languages: [{ target_language: 'en', active_id: 'v1' }],
    });
    versionsApiMocks.getChapterVersion.mockRejectedValue(new Error('boom'));
    const result = await mountHook();
    await act(async () => { await result.current.handleLanguageChange('en'); });
    expect(result.current.activeLanguage).toBe('zh');
    expect(result.current.blocks).toEqual(result.current.originalBlocks);
  });
});

describe('computeReadingStats', () => {
  it('counts Latin words at ~230wpm', () => {
    const blocks = [{ type: 'paragraph', content: [{ type: 'text', text: 'one two three four five' }] }];
    const stats = computeReadingStats(blocks as any, 'en');
    expect(stats.unit).toBe('words');
    expect(stats.minutes).toBeGreaterThanOrEqual(1);
  });

  it('counts CJK characters at ~400 chars/min for a ja/zh/ko language', () => {
    const blocks = [{ type: 'paragraph', content: [{ type: 'text', text: '你好世界' }] }];
    const stats = computeReadingStats(blocks as any, 'zh');
    expect(stats.unit).toBe('chars');
  });
});
