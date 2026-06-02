import { apiJson } from '@/api';
import type {
  ProposalListResponse,
  Proposal,
  PromoteResult,
  DetectGapsResponse,
  AutoEnrichResponse,
  SourceListResponse,
  Source,
  JobListResponse,
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
    },
    token: string,
  ): Promise<AutoEnrichResponse> {
    return apiJson<AutoEnrichResponse>(
      `${BASE}/projects/${bookId}/auto-enrich`,
      { method: 'POST', body: JSON.stringify({ book_id: bookId, ...body }), token },
    );
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
  ): Promise<{
    corpus_id: string;
    chunks_total: number;
    chunks_inserted: number;
    chunks_embedded: number;
  }> {
    return apiJson(`${BASE}/sources/${corpusId}/ingest`, {
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
};
