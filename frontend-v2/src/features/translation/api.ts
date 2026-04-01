import { apiJson } from '../../api';

export type ModelSource = 'user_model' | 'platform_model';

export type TranslationJobStatus =
  | 'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';

export type ChapterTranslationStatus =
  | 'pending' | 'running' | 'completed' | 'failed';

export type ChapterTranslation = {
  id: string;
  job_id: string;
  chapter_id: string;
  book_id: string;
  owner_user_id: string;
  status: ChapterTranslationStatus;
  translated_body: string | null;
  source_language: string | null;
  target_language: string;
  input_tokens: number | null;
  output_tokens: number | null;
  usage_log_id: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type TranslationJob = {
  job_id: string;
  book_id: string;
  owner_user_id: string;
  status: TranslationJobStatus;
  target_language: string;
  model_source: ModelSource;
  model_ref: string;
  chapter_ids: string[];
  total_chapters: number;
  completed_chapters: number;
  failed_chapters: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  chapter_translations?: ChapterTranslation[];
};

export type UserTranslationPreferences = {
  user_id: string;
  target_language: string;
  model_source: ModelSource;
  model_ref: string | null;
  system_prompt: string;
  user_prompt_tpl: string;
  chunk_size_tokens: number;
  invoke_timeout_secs: number;
  updated_at: string;
};

export type BookTranslationSettings = UserTranslationPreferences & {
  book_id: string;
  owner_user_id: string;
  is_default: boolean;
};

export type CoverageCell = {
  has_active: boolean;
  active_version_num: number | null;
  latest_version_num: number | null;
  latest_status: ChapterTranslationStatus | 'running' | null;
  version_count: number;
};

export type ChapterCoverage = {
  chapter_id: string;
  languages: Record<string, CoverageCell>;
};

export type BookCoverageResponse = {
  book_id: string;
  coverage: ChapterCoverage[];
  known_languages: string[];
};

export const translationApi = {
  getBookCoverage(token: string, bookId: string): Promise<BookCoverageResponse> {
    return apiJson(`/v1/translation/books/${bookId}/coverage`, { token });
  },

  createJob(token: string, bookId: string, payload: { chapter_ids: string[] }): Promise<TranslationJob> {
    return apiJson(`/v1/translation/books/${bookId}/jobs`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  listJobs(token: string, bookId: string, params?: { limit?: number; offset?: number }): Promise<TranslationJob[]> {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson(`/v1/translation/books/${bookId}/jobs${q ? '?' + q : ''}`, { token });
  },

  getJob(token: string, jobId: string): Promise<TranslationJob> {
    return apiJson(`/v1/translation/jobs/${jobId}`, { token });
  },

  cancelJob(token: string, jobId: string): Promise<void> {
    return apiJson(`/v1/translation/jobs/${jobId}/cancel`, { method: 'POST', token });
  },

  getPreferences(token: string): Promise<UserTranslationPreferences> {
    return apiJson('/v1/translation/preferences', { token });
  },

  getBookSettings(token: string, bookId: string): Promise<BookTranslationSettings> {
    return apiJson(`/v1/translation/books/${bookId}/settings`, { token });
  },

  putBookSettings(token: string, bookId: string, payload: Record<string, unknown>): Promise<BookTranslationSettings> {
    return apiJson(`/v1/translation/books/${bookId}/settings`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      token,
    });
  },
};
