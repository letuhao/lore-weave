import { apiJson } from '@/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type LeaderboardBook = {
  rank: number;
  book_id: string;
  owner_user_id: string;
  owner_display_name: string;
  title: string;
  genre_tags: string[];
  original_language: string | null;
  views: number;
  unique_readers: number;
  chapter_count: number;
  translation_count: number;
  avg_rating: number;
  rating_count: number;
  favorites_count: number;
  rank_change: number;
  has_cover: boolean;
};

export type LeaderboardAuthor = {
  rank: number;
  user_id: string;
  display_name: string;
  total_books: number;
  readers: number;
  avg_rating: number;
  total_chapters: number;
};

export type LeaderboardTranslator = {
  rank: number;
  user_id: string;
  display_name: string;
  total_chapters_done: number;
  languages: string[];
};

export type PagedResponse<T> = {
  items: T[];
  total: number;
  period: string;
};

// ── API ────────────────────────────────────────────────────────────────────

type BookParams = {
  period?: string;
  genre?: string;
  language?: string;
  sort?: string;
  limit?: number;
  offset?: number;
};

type ListParams = {
  period?: string;
  limit?: number;
  offset?: number;
};

function buildQs(params: Record<string, string | number | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `?${s}` : '';
}

export const leaderboardApi = {
  listBooks(params: BookParams = {}) {
    return apiJson<PagedResponse<LeaderboardBook>>(
      `/v1/leaderboard/books${buildQs(params)}`,
    );
  },

  listAuthors(params: ListParams = {}) {
    return apiJson<PagedResponse<LeaderboardAuthor>>(
      `/v1/leaderboard/authors${buildQs(params)}`,
    );
  },

  listTranslators(params: ListParams = {}) {
    return apiJson<PagedResponse<LeaderboardTranslator>>(
      `/v1/leaderboard/translators${buildQs(params)}`,
    );
  },
};
