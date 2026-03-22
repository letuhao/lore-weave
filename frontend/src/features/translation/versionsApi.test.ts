import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiJson } from '@/api';
import { versionsApi } from './versionsApi';

vi.mock('@/api', () => ({
  apiJson: vi.fn(),
}));

const TOKEN = 'test-token';
const BOOK_ID = 'book-uuid-1';
const CHAPTER_ID = 'chapter-uuid-1';
const VERSION_ID = 'version-uuid-1';

describe('versionsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── listChapterVersions ────────────────────────────────────────────────────

  it('listChapterVersions calls correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ chapter_id: CHAPTER_ID, languages: [] });
    await versionsApi.listChapterVersions(TOKEN, CHAPTER_ID);
    expect(apiJson).toHaveBeenCalledWith(
      `/v1/translation/chapters/${CHAPTER_ID}/versions`,
      { token: TOKEN },
    );
  });

  it('listChapterVersions returns the API response', async () => {
    const response = { chapter_id: CHAPTER_ID, languages: [] };
    vi.mocked(apiJson).mockResolvedValueOnce(response);
    const result = await versionsApi.listChapterVersions(TOKEN, CHAPTER_ID);
    expect(result).toEqual(response);
  });

  // ── getChapterVersion ──────────────────────────────────────────────────────

  it('getChapterVersion calls correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await versionsApi.getChapterVersion(TOKEN, CHAPTER_ID, VERSION_ID);
    expect(apiJson).toHaveBeenCalledWith(
      `/v1/translation/chapters/${CHAPTER_ID}/versions/${VERSION_ID}`,
      { token: TOKEN },
    );
  });

  // ── setActiveVersion ───────────────────────────────────────────────────────

  it('setActiveVersion sends PUT to correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await versionsApi.setActiveVersion(TOKEN, CHAPTER_ID, VERSION_ID);
    expect(apiJson).toHaveBeenCalledWith(
      `/v1/translation/chapters/${CHAPTER_ID}/versions/${VERSION_ID}/active`,
      { method: 'PUT', body: '{}', token: TOKEN },
    );
  });

  it('setActiveVersion uses PUT method (not GET or POST)', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await versionsApi.setActiveVersion(TOKEN, CHAPTER_ID, VERSION_ID);
    const callArgs = vi.mocked(apiJson).mock.calls[0][1] as { method?: string };
    expect(callArgs.method).toBe('PUT');
  });

  // ── getBookCoverage ────────────────────────────────────────────────────────

  it('getBookCoverage calls correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({ book_id: BOOK_ID, coverage: [], known_languages: [] });
    await versionsApi.getBookCoverage(TOKEN, BOOK_ID);
    expect(apiJson).toHaveBeenCalledWith(
      `/v1/translation/books/${BOOK_ID}/coverage`,
      { token: TOKEN },
    );
  });

  it('getBookCoverage returns the API response', async () => {
    const response = { book_id: BOOK_ID, coverage: [], known_languages: ['vi', 'zh'] };
    vi.mocked(apiJson).mockResolvedValueOnce(response);
    const result = await versionsApi.getBookCoverage(TOKEN, BOOK_ID);
    expect(result).toEqual(response);
  });

  // ── Error propagation ──────────────────────────────────────────────────────

  it('listChapterVersions propagates apiJson errors', async () => {
    const err = Object.assign(new Error('not found'), { status: 404, code: 'TRANSL_NOT_FOUND' });
    vi.mocked(apiJson).mockRejectedValueOnce(err);
    await expect(versionsApi.listChapterVersions(TOKEN, CHAPTER_ID)).rejects.toMatchObject({
      message: 'not found',
      status: 404,
    });
  });

  it('setActiveVersion propagates 422 errors', async () => {
    const err = Object.assign(new Error('not completed'), { status: 422, code: 'TRANSL_NOT_COMPLETED' });
    vi.mocked(apiJson).mockRejectedValueOnce(err);
    await expect(versionsApi.setActiveVersion(TOKEN, CHAPTER_ID, VERSION_ID)).rejects.toMatchObject({
      status: 422,
    });
  });
});
