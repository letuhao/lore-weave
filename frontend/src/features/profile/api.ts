import { apiJson } from '@/api';

// ── Types ──────────────────────────────────────────────────────────────────

export type PublicProfile = {
  user_id: string;
  display_name: string;
  avatar_url?: string;
  bio?: string;
  languages: string[];
  created_at: string;
  follower_count: number;
  following_count: number;
  is_following: boolean;
};

export type AuthorStats = {
  user_id: string;
  total_books: number;
  total_views: number;
  views_7d: number;
  views_30d: number;
  total_readers: number;
  avg_time_ms: number;
  total_chapters: number;
  avg_rating: number;
};

export type TranslatorStats = {
  user_id: string;
  display_name: string;
  total_translations: number;
  total_chapters_done: number;
  translations_7d: number;
  translations_30d: number;
  languages: string[];
};

export type CatalogBook = {
  book_id: string;
  owner_user_id: string;
  title: string;
  description: string | null;
  original_language: string | null;
  has_cover: boolean;
  cover_url: string | null;
  chapter_count: number;
  genre_tags: string[];
  view_count: number;
  created_at: string;
};

export type FollowUser = {
  user_id: string;
  display_name: string;
  avatar_url?: string;
};

export type PagedResponse<T> = {
  items: T[];
  total: number;
};

// ── API ────────────────────────────────────────────────────────────────────

export function fetchPublicProfile(userId: string, token?: string | null) {
  return apiJson<PublicProfile>(`/v1/users/${userId}`, { token });
}

export function fetchAuthorStats(userId: string) {
  return apiJson<AuthorStats>(`/v1/stats/authors/${userId}`);
}

export function fetchTranslatorStats(userId: string) {
  return apiJson<TranslatorStats>(`/v1/stats/translators/${userId}`);
}

export function fetchUserBooks(userId: string, params?: { limit?: number; offset?: number }) {
  const q = new URLSearchParams();
  q.set('author', userId);
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  return apiJson<PagedResponse<CatalogBook>>(`/v1/catalog/books?${q}`);
}

export function followUser(userId: string, token: string) {
  return apiJson<void>(`/v1/users/${userId}/follow`, { method: 'POST', token });
}

export function unfollowUser(userId: string, token: string) {
  return apiJson<void>(`/v1/users/${userId}/follow`, { method: 'DELETE', token });
}

export function fetchFollowers(userId: string, params?: { limit?: number; offset?: number }) {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  return apiJson<PagedResponse<FollowUser>>(`/v1/users/${userId}/followers?${q}`);
}

export function fetchFollowing(userId: string, params?: { limit?: number; offset?: number }) {
  const q = new URLSearchParams();
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  return apiJson<PagedResponse<FollowUser>>(`/v1/users/${userId}/following?${q}`);
}

export function addFavorite(bookId: string, token: string) {
  return apiJson<void>(`/v1/books/${bookId}/favorite`, { method: 'POST', token });
}

export function removeFavorite(bookId: string, token: string) {
  return apiJson<void>(`/v1/books/${bookId}/favorite`, { method: 'DELETE', token });
}
