import { apiJson } from '@/api';
import type {
  WikiArticleListResp,
  WikiArticleDetail,
  WikiRevisionListResp,
  WikiRevisionDetail,
  WikiSuggestionListResp,
  WikiSuggestionResp,
  WikiGenJobStatus,
  WikiGenerateResult,
  WikiGenConfig,
  WikiStalenessListResp,
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

  /**
   * Generate wiki articles. With no `model_ref` → deterministic stubs
   * (`{created}`). With a `model_ref` → DELEGATES to the LLM batch generator,
   * returning a job (`{job_id,status}`) or `{action:'none'}`; a 409 (active job)
   * is thrown by apiJson and handled by the caller.
   */
  generateStubs(
    bookId: string,
    body: {
      kind_codes?: string[];
      entity_ids?: string[];
      limit?: number;
      model_ref?: string;
      model_source?: string;
      max_spend_usd?: number;
    },
    token: string,
  ): Promise<WikiGenerateResult> {
    return apiJson(`${BASE}/books/${bookId}/wiki/generate`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  /* ── wiki-llm M7b — LLM-gen job lifecycle (glossary proxy → knowledge) ── */

  getJob(bookId: string, token: string): Promise<WikiGenJobStatus> {
    return apiJson<WikiGenJobStatus>(`${BASE}/books/${bookId}/wiki/job`, { token });
  },

  resumeJob(bookId: string, jobId: string, token: string): Promise<{ job_id: string; status: string }> {
    return apiJson(`${BASE}/books/${bookId}/wiki/job/${jobId}/resume`, {
      method: 'POST',
      token,
    });
  },

  cancelJob(bookId: string, jobId: string, token: string): Promise<{ job_id: string; status: string }> {
    return apiJson(`${BASE}/books/${bookId}/wiki/job/${jobId}/cancel`, {
      method: 'POST',
      token,
    });
  },

  /** Flat per-article wiki-gen cost estimate (D-WIKI-P2B-COST-ESTIMATE) — the FE
   *  multiplies by the selected-entity count for a pre-flight estimate. */
  getGenConfig(bookId: string, token: string): Promise<WikiGenConfig> {
    return apiJson<WikiGenConfig>(`${BASE}/books/${bookId}/wiki/gen-config`, { token });
  },

  /* ── wiki-llm Phase-2 — "Knowledge updates" change-feed (§5.3) ── */

  listStaleness(bookId: string, token: string): Promise<WikiStalenessListResp> {
    return apiJson<WikiStalenessListResp>(`${BASE}/books/${bookId}/wiki/staleness`, { token });
  },

  dismissStaleness(
    bookId: string,
    stalenessId: string,
    token: string,
  ): Promise<{ staleness_id: string; status: string }> {
    return apiJson(`${BASE}/books/${bookId}/wiki/staleness/${stalenessId}/dismiss`, {
      method: 'POST',
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
