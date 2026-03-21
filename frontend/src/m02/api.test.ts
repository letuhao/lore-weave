import { beforeEach, describe, expect, it, vi } from 'vitest';
import { m02Api } from './api';
import { apiJson } from '@/api';

vi.mock('@/api', () => ({
  apiJson: vi.fn(),
}));

describe('m02Api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('delegates listBooks to apiJson with token', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ items: [], total: 0 });
    await m02Api.listBooks('tok');
    expect(apiJson).toHaveBeenCalledWith('/v1/books', { token: 'tok' });
  });

  it('createChapter sends multipart with authorization header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => '{"chapter_id":"ch-1"}',
    });
    vi.stubGlobal('fetch', fetchMock);

    const file = new File(['hello'], 'chapter.txt', { type: 'text/plain' });
    await m02Api.createChapter('tok', 'book-1', {
      file,
      original_language: 'en',
      title: 'Chapter 1',
      sort_order: 3,
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/v1/books/book-1/chapters');
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
    expect(init.body).toBeInstanceOf(FormData);
  });

  it('createChapter throws enriched error for non-ok response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      text: async () => '{"code":"BOOK_CONFLICT","message":"failed"}',
    });
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['hello'], 'chapter.txt', { type: 'text/plain' });

    await expect(
      m02Api.createChapter('tok', 'book-1', { file, original_language: 'en' }),
    ).rejects.toMatchObject({
      message: 'failed',
      status: 409,
      code: 'BOOK_CONFLICT',
    });
  });

  it('createChapterEditor delegates JSON payload via apiJson', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({
      chapter_id: 'c1',
      book_id: 'b1',
      original_filename: 'editor-1.txt',
      original_language: 'vi',
      content_type: 'text/plain',
      byte_size: 0,
      sort_order: 1,
      lifecycle_state: 'active',
    } as never);

    await m02Api.createChapterEditor('tok', 'book-1', {
      original_language: 'vi',
      title: 'Editor chapter',
      body: 'hello',
    });

    expect(apiJson).toHaveBeenCalledWith('/v1/books/book-1/chapters', {
      method: 'POST',
      token: 'tok',
      body: JSON.stringify({
        original_language: 'vi',
        title: 'Editor chapter',
        body: 'hello',
      }),
    });
  });

  it('listChapters builds query string for filters and pagination', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ items: [], total: 0 } as never);
    await m02Api.listChapters('tok', 'book-1', {
      original_language: 'en',
      sort_order: 3,
      limit: 5,
      offset: 10,
      lifecycle_state: 'active',
    });
    expect(apiJson).toHaveBeenCalledWith(
      '/v1/books/book-1/chapters?lifecycle_state=active&original_language=en&sort_order=3&limit=5&offset=10',
      { token: 'tok' },
    );
  });

  it('downloadRaw sends authorized request and returns blob', async () => {
    const blob = new Blob(['raw-data'], { type: 'text/plain' });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => blob,
    });
    vi.stubGlobal('fetch', fetchMock);

    const got = await m02Api.downloadRaw('tok', 'book-1', 'chapter-1');
    expect(got).toBe(blob);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/v1/books/book-1/chapters/chapter-1/content'),
      expect.objectContaining({
        method: 'GET',
        headers: { Authorization: 'Bearer tok' },
      }),
    );
  });
});
