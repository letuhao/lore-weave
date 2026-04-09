import { apiJson } from '@/api';
import type {
  WikiArticleListResp,
  WikiArticleDetail,
  WikiRevisionListResp,
  WikiRevisionDetail,
  WikiSuggestionListResp,
  WikiSuggestionResp,
} from './types';

const BASE = '/v1/glossary';

export const wikiApi = {
  /* ── Article CRUD ── */

  listArticles(
    bookId: string,
    params: { status?: string; kind_code?: string; search?: string; limit?: number; offset?: number },
    token: string,
  ): Promise<WikiArticleListResp> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.kind_code) qs.set('kind_code', params.kind_code);
    if (params.search) qs.set('search', params.search);
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<WikiArticleListResp>(`${BASE}/books/${bookId}/wiki${q ? '?' + q : ''}`, { token });
  },

  getArticle(bookId: string, articleId: string, token: string): Promise<WikiArticleDetail> {
    return apiJson<WikiArticleDetail>(`${BASE}/books/${bookId}/wiki/${articleId}`, { token });
  },

  createArticle(
    bookId: string,
    body: { entity_id: string; template_code?: string; body_json?: unknown; status?: string },
    token: string,
  ): Promise<WikiArticleDetail> {
    return apiJson<WikiArticleDetail>(`${BASE}/books/${bookId}/wiki`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  patchArticle(
    bookId: string,
    articleId: string,
    body: { body_json?: unknown; status?: string; template_code?: string; spoiler_chapters?: string[]; summary?: string },
    token: string,
  ): Promise<WikiArticleDetail> {
    return apiJson<WikiArticleDetail>(`${BASE}/books/${bookId}/wiki/${articleId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
      token,
    });
  },

  deleteArticle(bookId: string, articleId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/books/${bookId}/wiki/${articleId}`, {
      method: 'DELETE',
      token,
    });
  },

  generateStubs(
    bookId: string,
    body: { kind_codes?: string[]; limit?: number },
    token: string,
  ): Promise<{ created: number; articles: unknown[] }> {
    return apiJson(`${BASE}/books/${bookId}/wiki/generate`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  /* ── Revisions ── */

  listRevisions(
    bookId: string,
    articleId: string,
    params: { limit?: number; offset?: number },
    token: string,
  ): Promise<WikiRevisionListResp> {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<WikiRevisionListResp>(
      `${BASE}/books/${bookId}/wiki/${articleId}/revisions${q ? '?' + q : ''}`,
      { token },
    );
  },

  getRevision(bookId: string, articleId: string, revId: string, token: string): Promise<WikiRevisionDetail> {
    return apiJson<WikiRevisionDetail>(
      `${BASE}/books/${bookId}/wiki/${articleId}/revisions/${revId}`,
      { token },
    );
  },

  restoreRevision(bookId: string, articleId: string, revId: string, token: string): Promise<WikiArticleDetail> {
    return apiJson<WikiArticleDetail>(
      `${BASE}/books/${bookId}/wiki/${articleId}/revisions/${revId}/restore`,
      { method: 'POST', token },
    );
  },

  /* ── Suggestions ── */

  listSuggestions(
    bookId: string,
    params: { status?: string; limit?: number; offset?: number },
    token: string,
  ): Promise<WikiSuggestionListResp> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<WikiSuggestionListResp>(
      `${BASE}/books/${bookId}/wiki/suggestions${q ? '?' + q : ''}`,
      { token },
    );
  },

  reviewSuggestion(
    bookId: string,
    articleId: string,
    sugId: string,
    body: { action: 'accept' | 'reject'; reviewer_note?: string },
    token: string,
  ): Promise<WikiSuggestionResp> {
    return apiJson<WikiSuggestionResp>(
      `${BASE}/books/${bookId}/wiki/${articleId}/suggestions/${sugId}`,
      { method: 'PATCH', body: JSON.stringify(body), token },
    );
  },
};
