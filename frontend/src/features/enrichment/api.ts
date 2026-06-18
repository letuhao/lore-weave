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
  ComposeDimension,
  ContextLicense,
  UploadResult,
  ResolvedIntent,
  ComposeTask,
  ComposeTaskAccepted,
} from './types';

const BASE = '/v1/lore-enrichment';

// LLM re-arch Phase 3 M2 — the interactive compose LLM calls (profile/suggest,
// compose/resolve-intent) run OFF the request path: POST → 202 + task_id, then
// poll the task to terminal. The submit+poll is hidden inside the two api methods
// so the hooks/components keep their existing "await the result" contract.
const COMPOSE_POLL_INTERVAL_MS = 1500;
// ~225s budget — MUST exceed the backend completion ceiling (complete.py's 180s LLM
// timeout + the pre-LLM HTTP for projection/chapters/KG/glossary). A shorter budget
// makes the FE abandon a task the worker then completes anyway → orphaned result +
// a duplicate LLM call on retry (/review-impl M2 #1).
const COMPOSE_POLL_MAX = 150;
const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function _pollComposeTask(taskId: string, token: string): Promise<ComposeTask> {
  let t = await enrichmentApi.getComposeTask(taskId, token);
  for (
    let i = 0;
    i < COMPOSE_POLL_MAX && (t.status === 'pending' || t.status === 'running');
    i++
  ) {
    await _sleep(COMPOSE_POLL_INTERVAL_MS);
    t = await enrichmentApi.getComposeTask(taskId, token);
  }
  return t;
}

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

  /** #1 dimension picker — list a kind's dimensions (id+label+required) for the
   *  compose chips. project_id := bookId in the path. */
  listComposeDimensions(
    bookId: string,
    kind: string,
    token: string,
    base = false,
  ): Promise<{ kind: string; dimensions: ComposeDimension[] }> {
    const qs = new URLSearchParams({ book_id: bookId, kind });
    if (base) qs.set('base', 'true'); // base set (override editor) vs effective (picker)
    return apiJson<{ kind: string; dimensions: ComposeDimension[] }>(
      `${BASE}/projects/${bookId}/dimensions?${qs.toString()}`,
      { token },
    );
  },

  /** Poll one async compose task (profile-suggest / intent-resolve). */
  getComposeTask(taskId: string, token: string): Promise<ComposeTask> {
    return apiJson<ComposeTask>(`${BASE}/compose-tasks/${taskId}`, { token });
  },

  /** Mode B step 1 — resolve a free-text intent into a proposed target (async:
   *  202 + task, then poll to terminal — Phase 3 M2). */
  async resolveIntent(
    bookId: string, intentText: string, genModel: string, token: string,
  ): Promise<ResolvedIntent> {
    const accepted = await apiJson<ComposeTaskAccepted>(
      `${BASE}/projects/${bookId}/compose/resolve-intent`,
      {
        method: 'POST',
        body: JSON.stringify({ book_id: bookId, intent_text: intentText, generation_model_ref: genModel }),
        token,
      },
    );
    const task = await _pollComposeTask(accepted.task_id, token);
    if (task.status !== 'completed' || !task.result) {
      throw new Error(task.error || 'intent resolve did not complete');
    }
    return task.result as ResolvedIntent;
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

  /** AI-suggest a DRAFT (not persisted). suggest_model_ref is a BYOK chat model.
   *  Async (Phase 3 M2): 202 + task, then poll to terminal for the draft. */
  async suggestBookProfile(
    bookId: string,
    body: { project_id: string; suggest_model_ref: string; sample_chapter_ids?: string[] },
    token: string,
  ): Promise<SuggestedProfile> {
    const accepted = await apiJson<ComposeTaskAccepted>(
      `${BASE}/books/${bookId}/profile/suggest`,
      { method: 'POST', body: JSON.stringify(body), token },
    );
    const task = await _pollComposeTask(accepted.task_id, token);
    if (task.status !== 'completed' || !task.result) {
      throw new Error(task.error || 'profile suggest did not complete');
    }
    return task.result as SuggestedProfile;
  },
};
