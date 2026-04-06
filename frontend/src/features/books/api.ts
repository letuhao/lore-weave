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
  genre_tags: string[];
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
  trashed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
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
    payload: { title: string; description?: string; original_language?: string; summary?: string; genre_tags?: string[] },
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
  async getOriginalContent(token: string, bookId: string, chapterId: string): Promise<string> {
    const res = await apiAuthedFetch(`/v1/books/${bookId}/chapters/${chapterId}/content`, token);
    if (!res.ok) throw new Error('Failed to load original content');
    return res.text();
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
      body: any;
      draft_format: string;
      draft_updated_at: string;
      draft_version: number;
      text_content: string | null;
    }>(`/v1/books/${bookId}/chapters/${chapterId}/draft`, { token });
  },
  patchDraft(
    token: string,
    bookId: string,
    chapterId: string,
    payload: { body: any; body_format?: string; commit_message?: string; expected_draft_version?: number },
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
    return apiJson<{ revision_id: string; created_at: string; message?: string; body: any; body_format: string; text_content: string | null }>(
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
    return apiJson<{
      book_id: string; title: string; description?: string | null;
      summary_excerpt?: string | null; original_language?: string | null;
      has_cover?: boolean; cover_url?: string | null;
      chapter_count?: number; visibility?: string;
    }>(
      `/v1/sharing/unlisted/${accessToken}`,
    );
  },
  listUnlistedChapters(accessToken: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiJson<{
      items: Array<{
        chapter_id: string; title?: string | null; sort_order: number;
        original_language: string; word_count_estimate?: number;
      }>;
      total: number; limit?: number; offset?: number;
    }>(
      `/v1/sharing/unlisted/${accessToken}/chapters${query ? `?${query}` : ''}`,
    );
  },
  getUnlistedChapter(accessToken: string, chapterId: string) {
    return apiJson<{
      chapter_id: string; title?: string | null; sort_order: number;
      original_language: string; body: any; text_content?: string;
    }>(
      `/v1/sharing/unlisted/${accessToken}/chapters/${chapterId}`,
    );
  },

  /** Upload chapter media (image) to MinIO. Uses XHR for progress tracking. */
  uploadChapterMedia(
    token: string,
    bookId: string,
    chapterId: string,
    file: File,
    onProgress?: (pct: number) => void,
    blockId?: string,
  ): Promise<{ url: string; object_key: string; filename: string; size: number; content_type: string; version?: number; version_id?: string }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      if (blockId) form.append('block_id', blockId);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${base()}/v1/books/${bookId}/chapters/${chapterId}/media`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        try {
          const body = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(body);
          } else {
            reject(Object.assign(new Error(body?.message || xhr.statusText), {
              status: xhr.status,
              code: body?.code,
            }));
          }
        } catch {
          reject(new Error('Invalid response'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error')));
      xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));

      xhr.send(form);
    });
  },

  /** Generate AI TTS audio for chapter blocks via AU-03 endpoint. */
  async generateAudio(
    token: string,
    bookId: string,
    chapterId: string,
    body: {
      language: string;
      voice: string;
      model_ref: string;
      model_source?: string;
      provider?: string;
      blocks: Array<{ index: number; text: string }>;
    },
  ): Promise<{ segments: Array<{ block_index: number; media_url: string; media_key: string; duration_ms: number }>; errors: Array<{ block_index: number; error: string }> }> {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/audio/generate`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data?.message || res.statusText), { status: res.status, code: data?.code });
    return data;
  },

  /** Upload block audio (mp3/wav/ogg/webm/m4a) to MinIO via AU-02 endpoint. */
  uploadBlockAudio(
    token: string,
    bookId: string,
    chapterId: string,
    file: File,
    blockIndex: number,
    subtitle?: string,
    onProgress?: (pct: number) => void,
  ): Promise<{ audio_url: string; media_key: string; duration_ms: number; size_bytes: number; content_type: string; subtitle: string }> {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      form.append('block_index', String(blockIndex));
      if (subtitle) form.append('subtitle', subtitle);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${base()}/v1/books/${bookId}/chapters/${chapterId}/block-audio`);
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        try {
          const body = JSON.parse(xhr.responseText);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(body);
          } else {
            reject(Object.assign(new Error(body?.message || xhr.statusText), {
              status: xhr.status,
              code: body?.code,
            }));
          }
        } catch {
          reject(new Error('Invalid response'));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error')));
      xhr.addEventListener('abort', () => reject(new Error('Upload cancelled')));

      xhr.send(form);
    });
  },

  // ── Media Versions ──────────────────────────────────────────────────

  async listMediaVersions(token: string, bookId: string, chapterId: string, blockId: string) {
    const res = await apiAuthedFetch(
      `/v1/books/${bookId}/chapters/${chapterId}/media-versions?block_id=${encodeURIComponent(blockId)}`,
      token,
    );
    const body = await res.json();
    if (!res.ok) throw Object.assign(new Error(body?.message || res.statusText), { status: res.status });
    return body as { items: MediaVersion[] };
  },

  async createMediaVersion(
    token: string, bookId: string, chapterId: string,
    body: { block_id: string; action: string; changes: string[]; prompt_snapshot?: string; caption_snapshot?: string; media_ref?: string },
  ) {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/media-versions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data?.message || res.statusText), { status: res.status });
    return data as MediaVersion;
  },

  async generateImage(
    token: string, bookId: string, chapterId: string,
    body: { block_id: string; prompt: string; model_source: string; model_ref: string; size?: string },
  ): Promise<{ url: string; object_key: string; version: number; version_id: string; ai_model: string; size: number; content_type: string }> {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/media-generate`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data?.message || res.statusText), { status: res.status, code: data?.code });
    return data;
  },

  async deleteMediaVersion(token: string, bookId: string, chapterId: string, versionId: string) {
    const res = await fetch(`${base()}/v1/books/${bookId}/chapters/${chapterId}/media-versions/${versionId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok && res.status !== 204) {
      const data = await res.json().catch(() => null);
      throw Object.assign(new Error(data?.message || res.statusText), { status: res.status });
    }
  },
};

// ── Types ───────────────────────────────────────────────────────────────

export type MediaVersion = {
  id: string;
  block_id: string;
  version: number;
  action: string;
  changes: string[];
  media_ref: string | null;
  media_url?: string | null;
  prompt_snapshot: string;
  caption_snapshot: string;
  ai_model: string | null;
  content_type: string | null;
  size_bytes: number | null;
  created_at: string;
};
