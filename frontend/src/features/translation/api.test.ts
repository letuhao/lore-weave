import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiJson } from '@/api';
import { translationApi } from './api';

vi.mock('@/api', () => ({
  apiJson: vi.fn(),
}));

const TOKEN = 'test-token';
const BOOK_ID = 'book-uuid-1';
const JOB_ID = 'job-uuid-1';
const CHAPTER_ID = 'chapter-uuid-1';

describe('translationApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Preferences ──────────────────────────────────────────────────────────────

  it('getPreferences calls correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await translationApi.getPreferences(TOKEN);
    expect(apiJson).toHaveBeenCalledWith('/v1/translation/preferences', { token: TOKEN });
  });

  it('putPreferences sends PUT with payload', async () => {
    const payload = {
      target_language: 'vi',
      model_source: 'platform_model' as const,
      model_ref: null,
      system_prompt: 'Translate.',
      user_prompt_tpl: 'Translate {chapter_text}',
    };
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await translationApi.putPreferences(TOKEN, payload);
    expect(apiJson).toHaveBeenCalledWith('/v1/translation/preferences', {
      method: 'PUT',
      body: JSON.stringify(payload),
      token: TOKEN,
    });
  });

  // ── Book settings ─────────────────────────────────────────────────────────────

  it('getBookSettings calls correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await translationApi.getBookSettings(TOKEN, BOOK_ID);
    expect(apiJson).toHaveBeenCalledWith(`/v1/translation/books/${BOOK_ID}/settings`, { token: TOKEN });
  });

  it('putBookSettings sends PUT with payload', async () => {
    const payload = {
      target_language: 'en',
      model_source: 'user_model' as const,
      model_ref: 'model-uuid',
      system_prompt: 'Custom.',
      user_prompt_tpl: 'Custom: {chapter_text}',
    };
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await translationApi.putBookSettings(TOKEN, BOOK_ID, payload);
    expect(apiJson).toHaveBeenCalledWith(`/v1/translation/books/${BOOK_ID}/settings`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      token: TOKEN,
    });
  });

  // ── Jobs ──────────────────────────────────────────────────────────────────────

  it('createJob sends POST with chapter_ids', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await translationApi.createJob(TOKEN, BOOK_ID, { chapter_ids: [CHAPTER_ID] });
    expect(apiJson).toHaveBeenCalledWith(`/v1/translation/books/${BOOK_ID}/jobs`, {
      method: 'POST',
      body: JSON.stringify({ chapter_ids: [CHAPTER_ID] }),
      token: TOKEN,
    });
  });

  it('listJobs calls without query params when none provided', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce([]);
    await translationApi.listJobs(TOKEN, BOOK_ID);
    expect(apiJson).toHaveBeenCalledWith(`/v1/translation/books/${BOOK_ID}/jobs`, { token: TOKEN });
  });

  it('listJobs appends limit and offset query params', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce([]);
    await translationApi.listJobs(TOKEN, BOOK_ID, { limit: 5, offset: 10 });
    expect(apiJson).toHaveBeenCalledWith(
      `/v1/translation/books/${BOOK_ID}/jobs?limit=5&offset=10`,
      { token: TOKEN },
    );
  });

  it('listJobs appends only provided params', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce([]);
    await translationApi.listJobs(TOKEN, BOOK_ID, { limit: 3 });
    expect(apiJson).toHaveBeenCalledWith(
      `/v1/translation/books/${BOOK_ID}/jobs?limit=3`,
      { token: TOKEN },
    );
  });

  it('getJob calls correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await translationApi.getJob(TOKEN, JOB_ID);
    expect(apiJson).toHaveBeenCalledWith(`/v1/translation/jobs/${JOB_ID}`, { token: TOKEN });
  });

  it('cancelJob sends POST to cancel endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce(undefined);
    await translationApi.cancelJob(TOKEN, JOB_ID);
    expect(apiJson).toHaveBeenCalledWith(`/v1/translation/jobs/${JOB_ID}/cancel`, {
      method: 'POST',
      token: TOKEN,
    });
  });

  it('getChapterTranslation calls correct endpoint', async () => {
    vi.mocked(apiJson).mockResolvedValueOnce({});
    await translationApi.getChapterTranslation(TOKEN, JOB_ID, CHAPTER_ID);
    expect(apiJson).toHaveBeenCalledWith(
      `/v1/translation/jobs/${JOB_ID}/chapters/${CHAPTER_ID}`,
      { token: TOKEN },
    );
  });

  // ── Error propagation ─────────────────────────────────────────────────────────

  it('propagates apiJson errors', async () => {
    const err = Object.assign(new Error('forbidden'), { status: 403, code: 'TRANSL_FORBIDDEN' });
    vi.mocked(apiJson).mockRejectedValueOnce(err);
    await expect(translationApi.getJob(TOKEN, JOB_ID)).rejects.toMatchObject({
      message: 'forbidden',
      status: 403,
      code: 'TRANSL_FORBIDDEN',
    });
  });
});
