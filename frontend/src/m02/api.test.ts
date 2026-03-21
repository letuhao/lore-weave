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
});
