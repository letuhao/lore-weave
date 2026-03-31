import { apiJson } from '@/api';

export type Visibility = 'private' | 'unlisted' | 'public';

export type Book = {
  book_id: string;
  owner_user_id: string;
  title: string;
  description?: string | null;
  original_language?: string | null;
  summary?: string | null;
  chapter_count: number;
  has_cover?: boolean;
  visibility?: Visibility;
  lifecycle_state: 'active' | 'trashed' | 'purge_pending';
  created_at?: string;
  updated_at?: string;
};

export type Chapter = {
  chapter_id: string;
  book_id: string;
  title?: string | null;
  original_filename: string;
  original_language: string;
  content_type: string;
  byte_size: number;
  sort_order: number;
  draft_updated_at?: string | null;
  draft_revision_count?: number;
  lifecycle_state: 'active' | 'trashed' | 'purge_pending';
};

const base = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';

export type ChapterListResponse = {
  items: Chapter[];
  total: number;
  limit?: number;
  offset?: number;
};

async function apiForm<T>(path: string, form: FormData, token: string): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw Object.assign(new Error(body?.message || res.statusText), {
      status: res.status,
      code: body?.code,
    });
  }
  return body as T;
}

async function apiAuthedFetch(path: string, token: string): Promise<Response> {
  return fetch(`${base()}${path}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export const booksApi = {
  listBooks(token: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{ items: Book[]; total: number }>(`/v1/books${query ? `?${query}` : ''}`, { token });
  },
  listTrash(token: string) {
    return apiJson<{ items: Book[]; total: number }>('/v1/books/trash', { token });
  },
  createBook(
    token: string,
    payload: { title: string; description?: string; original_language?: string; summary?: string },
  ) {
    return apiJson<Book>('/v1/books', { method: 'POST', token, body: JSON.stringify(payload) });
  },
  getBook(token: string, bookId: string) {
    return apiJson<Book>(`/v1/books/${bookId}`, { token });
  },
  patchBook(token: string, bookId: string, payload: Record<string, unknown>) {
    return apiJson<Book>(`/v1/books/${bookId}`, { method: 'PATCH', token, body: JSON.stringify(payload) });
  },
  trashBook(token: string, bookId: string) {
    return apiJson<void>(`/v1/books/${bookId}`, { method: 'DELETE', token });
  },
  restoreBook(token: string, bookId: string) {
    return apiJson<Book>(`/v1/books/${bookId}/restore`, { method: 'POST', token });
  },
  purgeBook(token: string, bookId: string) {
    return apiJson<void>(`/v1/books/${bookId}/purge`, { method: 'DELETE', token });
  },
  uploadCover(token: string, bookId: string, file: File) {
    const form = new FormData();
    form.append('file', file);
    return apiForm<Book>(`/v1/books/${bookId}/cover`, form, token);
  },
  listChapters(
    token: string,
    bookId: string,
    params?: { lifecycle_state?: string; original_language?: string; sort_order?: number; limit?: number; offset?: number },
  ) {
    const qs = new URLSearchParams();
    if (params?.lifecycle_state) qs.set('lifecycle_state', params.lifecycle_state);
    if (params?.original_language) qs.set('original_language', params.original_language);
    if (params?.sort_order !== undefined) qs.set('sort_order', String(params.sort_order));
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<ChapterListResponse>(`/v1/books/${bookId}/chapters${query ? `?${query}` : ''}`, { token });
  },
  createChapterUpload(
    token: string,
    bookId: string,
    payload: { file: File; original_language: string; title?: string; sort_order?: number },
  ) {
    const form = new FormData();
    form.append('file', payload.file);
    form.append('original_language', payload.original_language);
    if (payload.title) form.append('title', payload.title);
    if (payload.sort_order !== undefined) form.append('sort_order', String(payload.sort_order));
    return apiForm<Chapter>(`/v1/books/${bookId}/chapters`, form, token);
  },
  createChapter(token: string, bookId: string, payload: { file: File; original_language: string; title?: string; sort_order?: number }) {
    return this.createChapterUpload(token, bookId, payload);
  },
  createChapterEditor(
    token: string,
    bookId: string,
    payload: { original_language: string; title?: string; sort_order?: number; body?: string },
  ) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters`, {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  async downloadRaw(token: string, bookId: string, chapterId: string) {
    const res = await apiAuthedFetch(`/v1/books/${bookId}/chapters/${chapterId}/export`, token);
    if (!res.ok) {
      const text = await res.text();
      let message = res.statusText;
      try {
        const body = JSON.parse(text) as { message?: string };
        message = body.message || message;
      } catch {
        // keep status text fallback
      }
      throw new Error(message);
    }
    return res.blob();
  },
  getChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}`, { token });
  },
  patchChapter(token: string, bookId: string, chapterId: string, payload: Record<string, unknown>) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  trashChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<void>(`/v1/books/${bookId}/chapters/${chapterId}`, { method: 'DELETE', token });
  },
  restoreChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<Chapter>(`/v1/books/${bookId}/chapters/${chapterId}/restore`, { method: 'POST', token });
  },
  purgeChapter(token: string, bookId: string, chapterId: string) {
    return apiJson<void>(`/v1/books/${bookId}/chapters/${chapterId}/purge`, { method: 'DELETE', token });
  },
  getDraft(token: string, bookId: string, chapterId: string) {
    return apiJson<{
      chapter_id: string;
      body: string;
      draft_format: string;
      draft_updated_at: string;
      draft_version: number;
    }>(`/v1/books/${bookId}/chapters/${chapterId}/draft`, { token });
  },
  patchDraft(
    token: string,
    bookId: string,
    chapterId: string,
    payload: { body: string; commit_message?: string; expected_draft_version?: number },
  ) {
    return apiJson(`/v1/books/${bookId}/chapters/${chapterId}/draft`, {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },
  listRevisions(token: string, bookId: string, chapterId: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{ items: Array<{ revision_id: string; created_at: string; message?: string }>; total: number }>(
      `/v1/books/${bookId}/chapters/${chapterId}/revisions${query ? `?${query}` : ''}`,
      { token },
    );
  },
  getRevision(token: string, bookId: string, chapterId: string, revisionId: string) {
    return apiJson<{ revision_id: string; created_at: string; message?: string; body: string }>(
      `/v1/books/${bookId}/chapters/${chapterId}/revisions/${revisionId}`,
      { token },
    );
  },
  restoreRevision(token: string, bookId: string, chapterId: string, revisionId: string) {
    return apiJson(`/v1/books/${bookId}/chapters/${chapterId}/revisions/${revisionId}/restore`, {
      method: 'POST',
      token,
    });
  },
  getCover(token: string, bookId: string): Promise<Blob> {
    return fetch(`${base()}/v1/books/${bookId}/cover`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((r) => {
      if (!r.ok) throw new Error('cover not found');
      return r.blob();
    });
  },
  getSharing(token: string, bookId: string) {
    return apiJson<{ book_id: string; visibility: 'private' | 'unlisted' | 'public'; unlisted_access_token?: string }>(
      `/v1/sharing/books/${bookId}`,
      { token },
    );
  },
  patchSharing(
    token: string,
    bookId: string,
    payload: { visibility?: 'private' | 'unlisted' | 'public'; rotate_unlisted_token?: boolean },
  ) {
    return apiJson(`/v1/sharing/books/${bookId}`, { method: 'PATCH', token, body: JSON.stringify(payload) });
  },
  listCatalog(params?: { limit?: number; offset?: number; q?: string }) {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    if (params?.q) qs.set('q', params.q);
    const query = qs.toString();
    return apiJson<{
      items: Array<{ book_id: string; title: string; summary_excerpt?: string; original_language?: string; chapter_count?: number }>;
      total: number;
    }>(
      `/v1/catalog/books${query ? `?${query}` : ''}`,
    );
  },
  getCatalogBook(bookId: string) {
    return apiJson<{ book_id: string; title: string; summary_excerpt?: string; original_language?: string; chapter_count?: number }>(
      `/v1/catalog/books/${bookId}`,
    );
  },
  listCatalogChapters(bookId: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{ items: Array<{ chapter_id: string; title?: string | null; sort_order: number; original_language: string }>; total: number; limit?: number; offset?: number }>(
      `/v1/catalog/books/${bookId}/chapters${query ? `?${query}` : ''}`,
    );
  },
  getCatalogChapter(bookId: string, chapterId: string) {
    return apiJson<{ chapter_id: string; title?: string | null; sort_order: number; original_language: string; body: string }>(
      `/v1/catalog/books/${bookId}/chapters/${chapterId}`,
    );
  },
  getUnlisted(accessToken: string) {
    return apiJson<{ book_id: string; title: string; summary_excerpt?: string; original_language?: string; chapter_count?: number }>(
      `/v1/sharing/unlisted/${accessToken}`,
    );
  },
  listUnlistedChapters(accessToken: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{ items: Array<{ chapter_id: string; title?: string | null; sort_order: number; original_language: string }>; total: number; limit?: number; offset?: number }>(
      `/v1/sharing/unlisted/${accessToken}/chapters${query ? `?${query}` : ''}`,
    );
  },
  getUnlistedChapter(accessToken: string, chapterId: string) {
    return apiJson<{ chapter_id: string; title?: string | null; sort_order: number; original_language: string; body: string }>(
      `/v1/sharing/unlisted/${accessToken}/chapters/${chapterId}`,
    );
  },
};
