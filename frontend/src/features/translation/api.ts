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
  version_num: number;
  status: ChapterTranslationStatus;
  translated_body: string | null;
  translated_body_json: Record<string, unknown>[] | null;
  translated_body_format: 'text' | 'json';
  source_language: string | null;
  target_language: string;
  input_tokens: number | null;
  output_tokens: number | null;
  usage_log_id: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  // V3 quality rollup (M5a). null/0 for V2 chapters.
  quality_score: number | null;
  unresolved_high_count: number;
  qa_rounds_used: number;
  // M5c: true when a glossary change post-dates this translation.
  is_glossary_stale: boolean;
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
  // M6b-2: active version's glossary-staleness (fallback latest). Legacy rows
  // default false (additive — old servers omit it).
  is_glossary_stale?: boolean;
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

// ── Version types ─────────────────────────────────────────────────────────────

export type VersionSummary = {
  id: string;
  version_num: number;
  job_id: string;
  status: ChapterTranslationStatus;
  is_active: boolean;
  model_source: string;
  model_ref: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
  authored_by: string;
};

export type LanguageVersionGroup = {
  target_language: string;
  active_id: string | null;
  versions: VersionSummary[];
};

export type ChapterVersionsResponse = {
  chapter_id: string;
  languages: LanguageVersionGroup[];
};

export type ActiveVersionResponse = {
  chapter_id: string;
  target_language: string;
  active_id: string;
};

// ── Version API ───────────────────────────────────────────────────────────────

export const versionsApi = {
  listChapterVersions(token: string, chapterId: string): Promise<ChapterVersionsResponse> {
    return apiJson(`/v1/translation/chapters/${chapterId}/versions`, { token });
  },

  getChapterVersion(token: string, chapterId: string, versionId: string): Promise<ChapterTranslation> {
    return apiJson(`/v1/translation/chapters/${chapterId}/versions/${versionId}`, { token });
  },

  setActiveVersion(
    token: string, chapterId: string, versionId: string, acknowledgeIssues = false,
  ): Promise<ActiveVersionResponse> {
    const q = acknowledgeIssues ? '?acknowledge_issues=true' : '';
    return apiJson(`/v1/translation/chapters/${chapterId}/versions/${versionId}/active${q}`, {
      method: 'PUT',
      token,
    });
  },

  // M7c: save a human-edited translation as a new version. The LLM→human diff is
  // captured as learning gold server-side (translation.corrected).
  saveEditedVersion(
    token: string,
    chapterId: string,
    payload: {
      target_language: string;
      edited_from_version_id: string;
      translated_body?: string;
      translated_body_json?: unknown[];
      translated_body_format: 'text' | 'json';
    },
  ): Promise<ChapterTranslation> {
    return apiJson(`/v1/translation/chapters/${chapterId}/versions/edit`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  // T1: correct a single translated block in the chapter's (one) human-version.
  // First call get-or-creates the human-version (seeded from base_version_id) + makes
  // it active; later calls patch it in place. Per-block LLM→human gold is captured
  // server-side. Block (json) format only.
  patchBlock(
    token: string,
    chapterId: string,
    payload: {
      target_language: string;
      base_version_id: string;
      block_index: number;
      block: Record<string, unknown>;
      source_block_text?: string;
    },
  ): Promise<ChapterTranslation> {
    return apiJson(`/v1/translation/chapters/${chapterId}/versions/blocks`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
};

// ── Translation API ───────────────────────────────────────────────────────────

export const translationApi = {
  getBookCoverage(token: string, bookId: string): Promise<BookCoverageResponse> {
    return apiJson(`/v1/translation/books/${bookId}/coverage`, { token });
  },

  createJob(
    token: string,
    bookId: string,
    payload: {
      chapter_ids: string[];
      // Per-job overrides (T1 Fix-C): when set, the job uses these directly and does
      // not depend on book translation settings having been persisted first.
      target_language?: string;
      model_source?: string;
      model_ref?: string;
      // Quality verification (V3): the verifier→correct loop only runs in pipeline
      // 'v3', so the UI sends pipeline_version='v3' when verification is enabled. The
      // verifier model is optional (falls back to the translator). qa_depth/rounds
      // tune the loop. Omitted → backend defaults (v2, no verify).
      pipeline_version?: 'v2' | 'v3';
      qa_depth?: 'rule_only' | 'standard' | 'thorough';
      max_qa_rounds?: number;
      verifier_model_source?: string;
      verifier_model_ref?: string;
      // Bypass the idempotency skip-gate so an already-translated chapter is
      // re-translated (and a new version produced) rather than skipped.
      force_retranslate?: boolean;
    },
  ): Promise<TranslationJob> {
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

  putPreferences(token: string, payload: Partial<UserTranslationPreferences>): Promise<UserTranslationPreferences> {
    return apiJson('/v1/translation/preferences', {
      method: 'PUT',
      body: JSON.stringify(payload),
      token,
    });
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
