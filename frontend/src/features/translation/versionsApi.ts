import { apiJson } from '../../api';
import type { ChapterTranslation, ChapterTranslationStatus, ModelSource } from './api';

export type VersionSummary = {
  id: string;
  version_num: number;
  job_id: string;
  status: ChapterTranslationStatus;
  is_active: boolean;
  model_source: ModelSource;
  model_ref: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
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

export const versionsApi = {
  listChapterVersions(token: string, chapterId: string): Promise<ChapterVersionsResponse> {
    return apiJson(`/v1/translation/chapters/${chapterId}/versions`, { token });
  },

  getChapterVersion(token: string, chapterId: string, versionId: string): Promise<ChapterTranslation> {
    return apiJson(`/v1/translation/chapters/${chapterId}/versions/${versionId}`, { token });
  },

  setActiveVersion(token: string, chapterId: string, versionId: string): Promise<ActiveVersionResponse> {
    return apiJson(`/v1/translation/chapters/${chapterId}/versions/${versionId}/active`, {
      method: 'PUT',
      body: '{}',
      token,
    });
  },

  getBookCoverage(token: string, bookId: string): Promise<BookCoverageResponse> {
    return apiJson(`/v1/translation/books/${bookId}/coverage`, { token });
  },
};
