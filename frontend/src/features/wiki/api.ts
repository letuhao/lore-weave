import { apiJson } from '@/api';
import type {
  WikiArticleListResp,
  WikiArticleDetail,
  WikiRevisionListResp,
} from './types';

const BASE = '/v1/glossary';

export const wikiApi = {
  /* ── Owner endpoints (require auth) ── */

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
};
