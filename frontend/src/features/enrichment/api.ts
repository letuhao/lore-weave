import { apiJson, apiBase } from '@/api';
import type {
  ProposalListResponse,
  Proposal,
  PromoteResult,
  DetectGapsResponse,
  AutoEnrichResponse,
  EnrichTarget,
  SourceListResponse,
  Source,
  IngestResult,
  GroundResult,
  JobListResponse,
  BookProfile,
  BookProfileInput,
  SuggestedProfile,
  ComposeBody,
  ComposeResult,
  ContextLicense,
  UploadResult,
  ResolvedIntent,
} from './types';

const BASE = '/v1/lore-enrichment';

// Enrichment is BOOK-bound, so the GUI scopes by `book_id`. The backend's
// project-scoped routes (per-proposal actions, detect-gaps / auto-enrich / sources)
// use `project_id := bookId` as the book's default enrichment scope. The per-proposal
// ACTIONS use the proposal's OWN `project_id` (rows can span general projects, so the
// project filter is derived client-side from the list).
export const enrichmentApi = {
  // ── proposals — list by book; read/act by the row's project_id ──────────────
  listProposals(
    bookId: string,
    params: { review_status?: string; limit?: number; offset?: number },
    token: string,
  ): Promise<ProposalListResponse> {
    const qs = new URLSearchParams({ book_id: bookId });
    if (params.review_status) qs.set('review_status', params.review_status);
    qs.set('limit', String(params.limit ?? 100));
    if (params.offset) qs.set('offset', String(params.offset));
    return apiJson<ProposalListResponse>(`${BASE}/proposals?${qs.toString()}`, { token });
  },

  getProposal(proposalId: string, projectId: string, token: string): Promise<Proposal> {
    return apiJson<Proposal>(
      `${BASE}/proposals/${proposalId}?project_id=${projectId}`,
      { token },
    );
  },

  approve(proposalId: string, projectId: string, token: string): Promise<Proposal> {
    return apiJson<Proposal>(
      `${BASE}/proposals/${proposalId}/approve?project_id=${projectId}`,
      { method: 'POST', token },
    );
  },

  reject(
    proposalId: string,
    projectId: string,
    reason: string | undefined,
    token: string,
  ): Promise<Proposal> {
    return apiJson<Proposal>(
      `${BASE}/proposals/${proposalId}/reject?project_id=${projectId}`,
      { method: 'POST', body: JSON.stringify({ reason }), token },
    );
  },

  edit(
    proposalId: string,
    projectId: string,
    content: string,
    token: string,
  ): Promise<Proposal> {
    return apiJson<Proposal>(
      `${BASE}/proposals/${proposalId}/edit?project_id=${projectId}`,
      { method: 'POST', body: JSON.stringify({ content }), token },
    );
  },

  /** The ④ gate — author-only promote to glossary canon. Needs the book anchor. */
  promote(
    proposalId: string,
    projectId: string,
    bookId: string,
    token: string,
  ): Promise<PromoteResult> {
    return apiJson<PromoteResult>(
      `${BASE}/proposals/${proposalId}/promote?project_id=${projectId}`,
      { method: 'POST', body: JSON.stringify({ book_id: bookId }), token },
    );
  },

  retract(
    proposalId: string,
    projectId: string,
    bookId: string,
    token: string,
  ): Promise<unknown> {
    return apiJson<unknown>(
      `${BASE}/proposals/${proposalId}/retract?project_id=${projectId}`,
      { method: 'POST', body: JSON.stringify({ book_id: bookId }), token },
    );
  },

  // ── gaps — project_id := bookId in the path ─────────────────────────────────
  detectGaps(bookId: string, token: string): Promise<DetectGapsResponse> {
    return apiJson<DetectGapsResponse>(
      `${BASE}/projects/${bookId}/detect-gaps`,
      { method: 'POST', body: JSON.stringify({ book_id: bookId }), token },
    );
  },

  autoEnrich(
    bookId: string,
    body: {
      embedding_model_ref: string;
      generation_model_ref: string;
      technique?: string;
      max_gaps?: number;
      max_spend_usd?: number | null;
      top_k?: number;
      /** LE-064 — when set, enrich exactly these gaps (per-row "enrich →"). */
      targets?: EnrichTarget[];
    },
    token: string,
  ): Promise<AutoEnrichResponse> {
    return apiJson<AutoEnrichResponse>(
      `${BASE}/projects/${bookId}/auto-enrich`,
      { method: 'POST', body: JSON.stringify({ book_id: bookId, ...body }), token },
    );
  },

  /** Compose — the unified async input entry (slice 1: gap | draft). project_id :=
   *  bookId in the path; body carries book_id := bookId. Returns 202 + job_id. */
  compose(bookId: string, body: ComposeBody, token: string): Promise<ComposeResult> {
    return apiJson<ComposeResult>(`${BASE}/projects/${bookId}/compose`, {
      method: 'POST',
      body: JSON.stringify({ book_id: bookId, ...body }),
      token,
    });
  },

  // ── uploads (mode F) — multipart upload + poll. project_id := bookId. ─────────
  /** Upload a file (multipart). Returns 202 + {upload_id, status:'processing'};
   *  poll getUpload until ready/failed. Uses a raw fetch (apiJson is JSON-only). */
  async uploadFile(
    bookId: string,
    file: File,
    license: ContextLicense,
    token: string,
  ): Promise<UploadResult> {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('book_id', bookId);
    fd.append('project_id', bookId);
    fd.append('license_asserted', license);
    const res = await fetch(`${apiBase()}${BASE}/uploads`, {
      method: 'POST',
      body: fd, // no Content-Type → the browser sets the multipart boundary
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const text = await res.text();
    const body = text ? JSON.parse(text) : null;
    if (!res.ok) throw new Error(body?.message || res.statusText);
    return body as UploadResult;
  },

  /** Poll an upload's extraction status. */
  getUpload(uploadId: string, token: string): Promise<UploadResult> {
    return apiJson<UploadResult>(`${BASE}/uploads/${uploadId}`, { token });
  },

  /** Mode B step 1 — resolve a free-text intent into a proposed target (no job). */
  resolveIntent(bookId: string, intentText: string, genModel: string, token: string): Promise<ResolvedIntent> {
    return apiJson<ResolvedIntent>(`${BASE}/projects/${bookId}/compose/resolve-intent`, {
      method: 'POST',
      body: JSON.stringify({ book_id: bookId, intent_text: intentText, generation_model_ref: genModel }),
      token,
    });
  },

  // ── sources (corpus) — project_id := bookId ─────────────────────────────────
  listSources(bookId: string, token: string): Promise<SourceListResponse> {
    return apiJson<SourceListResponse>(
      `${BASE}/sources?project_id=${bookId}&limit=100`,
      { token },
    );
  },

  registerSource(
    bookId: string,
    body: { name: string; kind: string; license?: string },
    token: string,
  ): Promise<Source> {
    return apiJson<Source>(`${BASE}/sources`, {
      method: 'POST',
      body: JSON.stringify({ project_id: bookId, ...body }),
      token,
    });
  },

  ingestSource(
    corpusId: string,
    bookId: string,
    body: { text: string; embedding_model_ref: string; target_chars?: number },
    token: string,
  ): Promise<IngestResult> {
    return apiJson<IngestResult>(`${BASE}/sources/${corpusId}/ingest`, {
      method: 'POST',
      body: JSON.stringify({ project_id: bookId, ...body }),
      token,
    });
  },

  /** C2 chapter-selection grounding ingest — author picks chapters (a selection
   *  LIST) to embed as a grounding corpus. project_id := bookId. */
  groundFromBook(
    bookId: string,
    body: { embedding_model_ref: string; chapter_ids: string[]; target_chars?: number },
    token: string,
  ): Promise<GroundResult> {
    return apiJson<GroundResult>(`${BASE}/books/${bookId}/ground`, {
      method: 'POST',
      body: JSON.stringify({ project_id: bookId, ...body }),
      token,
    });
  },

  // ── jobs — list by book; resume by the job's project_id ─────────────────────
  listJobs(bookId: string, token: string): Promise<JobListResponse> {
    return apiJson<JobListResponse>(`${BASE}/jobs?book_id=${bookId}&limit=50`, { token });
  },

  resumeJob(
    jobId: string,
    projectId: string,
    token: string,
  ): Promise<{ job_id: string; status: string; resume?: string }> {
    return apiJson(`${BASE}/jobs/${jobId}/resume?project_id=${projectId}`, {
      method: 'POST',
      token,
    });
  },

  // ── book profile (de-bias C3) — book-scoped, owner-only ─────────────────────
  getBookProfile(bookId: string, token: string): Promise<BookProfile> {
    return apiJson<BookProfile>(`${BASE}/books/${bookId}/profile`, { token });
  },

  /** FULL REPLACE (REST PUT): the caller MUST send the whole profile — an omitted
   *  field resets to its default (e.g. omitting markers clears them). */
  putBookProfile(
    bookId: string,
    body: BookProfileInput,
    token: string,
  ): Promise<BookProfile> {
    return apiJson<BookProfile>(`${BASE}/books/${bookId}/profile`, {
      method: 'PUT',
      body: JSON.stringify(body),
      token,
    });
  },

  /** AI-suggest a DRAFT (not persisted). suggest_model_ref is a BYOK chat model. */
  suggestBookProfile(
    bookId: string,
    body: { project_id: string; suggest_model_ref: string; sample_chapter_ids?: string[] },
    token: string,
  ): Promise<SuggestedProfile> {
    return apiJson<SuggestedProfile>(`${BASE}/books/${bookId}/profile/suggest`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },
};
