// Narrative Motif Library (W6) — the motif API layer. Relative `/v1/composition/*`
// rides the Vite proxy → gateway (dev :3123) / nginx (prod). W6 builds against the
// FROZEN F0 §3.6 shapes; the W1/W2/W3/W5 endpoints below are the contract — until
// they land, tests mock `apiJson` (the existing api.poll.test.ts pattern).
//
// Tier-W ops (adopt/mine/conformance-run/bind→generate) are a TWO-STEP mint→confirm
// flow: the FE NEVER executes the spend — it mints a cost estimate + confirm_token,
// the human confirms, the FE POSTs the token to the actions route, the server runs
// the effect + a job we poll (the existing GenerationJob poll machinery).
import { apiJson } from '../../../api';
import { mcpExecute } from '../../../mcpBridge';
import { compositionApi } from '../api';
import type { GenerationJob } from '../types';
import type {
  ArcConformance, CatalogList, ChapterConformance, CostEstimate, MineResult, Motif,
  MotifCreateArgs, MotifPatchArgs, MotifTier, SyncDiff, SyncResult,
} from './types';

const BASE = '/v1/composition';

// ── the motif graph (BE-M3) edge shapes ──────────────────────────────────────
export type MotifLinkKind = 'composed_of' | 'precedes' | 'variant_of';
export type MotifLinkDirection = 'out' | 'in' | 'both';
/** One relationship edge as GET /motifs/{id}/links returns it — the edge id/kind/ord/
 *  direction plus the NEIGHBOR stub (id/code/name), so a list needs no second fetch. */
export type MotifLinkRow = {
  id: string;
  kind: MotifLinkKind;
  ord: number | null;
  direction: 'out' | 'in';
  neighbor_id: string;
  neighbor_code: string;
  neighbor_name: string;
};

// One ranked suggest candidate (BE-M4): the motif + its score + the "why this motif"
// breakdown (tension/genre/precondition/cosine, optionally degraded).
export type MotifSuggestion = {
  motif: Motif;
  score: number;
  match_reason: Record<string, unknown>;
};

/** GET /motifs scope — the router accepts ONLY mine|system|all (NOT 'public';
 *  others' public rows are the CATALOG route, never this list). */
export type MotifListParams = {
  scope?: 'all' | 'system' | 'mine';
  genre?: string;
  kind?: string;
  status?: string;
  q?: string;
  language?: string;
  limit?: number;
  offset?: number;   // §2#9 scale — paginate a >limit library
};

/** GET /motifs/catalog params — the catalog route has NO scope (always public)
 *  and paginates with sort/offset instead. */
export type CatalogParams = {
  genre?: string;
  kind?: string;
  q?: string;
  language?: string;
  sort?: 'recent' | 'name';
  limit?: number;
  offset?: number;
};

function _qs(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export const motifApi = {
  // ── library CRUD (W1) ──────────────────────────────────────────────────────
  list(params: MotifListParams, token: string): Promise<{ motifs: Motif[] }> {
    return apiJson<{ motifs: Motif[] }>(`${BASE}/motifs${_qs(params)}`, { token });
  },
  get(motifId: string, token: string): Promise<Motif> {
    return apiJson<Motif>(`${BASE}/motifs/${motifId}`, { token });
  },
  create(args: MotifCreateArgs, token: string): Promise<Motif> {
    return apiJson<Motif>(`${BASE}/motifs`, {
      method: 'POST', body: JSON.stringify(args), token,
    });
  },
  patch(motifId: string, args: MotifPatchArgs, expectedVersion: number, token: string): Promise<Motif> {
    return apiJson<Motif>(`${BASE}/motifs/${motifId}`, {
      method: 'PATCH',
      body: JSON.stringify(args),
      headers: { 'If-Match': String(expectedVersion) },
      token,
    });
  },
  archive(motifId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/motifs/${motifId}`, { method: 'DELETE', token });
  },

  // ── catalog (W1 — the B-3 allow-list projection) ───────────────────────────
  // Hits GET /motifs/catalog → list_public (the _CATALOG_COLS allow-list), NOT
  // GET /motifs with scope='public' (which 422s AND would bypass the allow-list).
  // Answers the `{ items, total, limit, offset }` envelope, NOT `{ motifs }`.
  catalog(params: CatalogParams, token: string): Promise<CatalogList> {
    return apiJson<CatalogList>(`${BASE}/motifs/catalog${_qs(params)}`, { token });
  },

  // ── the book's library (3a) — GET /motifs/book/{book_id}. Returns, MERGED in one
  //    list: the caller's globals (the Mine tier) + this book's private labels + its
  //    book_shared rows. Every row carries book_id + book_shared, so the FE partitions
  //    ONE response into the Book tab (book_id===bookId && !book_shared) and the Shared
  //    tab (book_shared===true) — do NOT fetch it twice (§3.1).
  book(bookId: string, token: string,
       params?: { genre?: string; kind?: string; status?: string; q?: string }): Promise<{ motifs: Motif[] }> {
    return apiJson<{ motifs: Motif[] }>(`${BASE}/motifs/book/${bookId}${_qs(params ?? {})}`, { token });
  },

  // ── the motif graph (BE-M3, 3a-C) — composed_of · precedes · variant_of ─────
  links(motifId: string, token: string,
        opts?: { direction?: MotifLinkDirection; bookId?: string | null }): Promise<{ motif_id: string; links: MotifLinkRow[]; count: number }> {
    return apiJson(`${BASE}/motifs/${motifId}/links${_qs({ direction: opts?.direction, book_id: opts?.bookId ?? undefined })}`, { token });
  },
  createLink(motifId: string, args: { to_motif_id: string; kind: MotifLinkKind; ord?: number | null; book_id?: string | null }, token: string): Promise<MotifLinkRow> {
    return apiJson<MotifLinkRow>(`${BASE}/motifs/${motifId}/links`, {
      method: 'POST', body: JSON.stringify(args), token,
    });
  },
  deleteLink(linkId: string, token: string, bookId?: string | null): Promise<{ deleted: boolean; link_id: string }> {
    return apiJson(`${BASE}/motif-links/${linkId}${_qs({ book_id: bookId ?? undefined })}`, { method: 'DELETE', token });
  },

  // ── ranked suggest (BE-M4, 3b) — the GUI twin of composition_motif_suggest_for_chapter,
  //    replacing the flat list(scope=all,100) behind SwapMotifPopover (GG-1 Determinism).
  suggestForChapter(projectId: string, nodeId: string, token: string, limit = 5): Promise<{ candidates: MotifSuggestion[] }> {
    return apiJson(`${BASE}/works/${projectId}/scenes/${nodeId}/suggest-motifs${_qs({ limit })}`, { token });
  },

  // ── Tier-W: adopt = clone into YOUR library (R2.8 confirm-token), via the
  //    FE→MCP-tool bridge. Adopt defaults to the user's GLOBAL tier; passing a bookId
  //    LABELS the clone with that book (D-MOTIF-ADOPT-PER-BOOK = model A book-scoped
  //    filter — the clone is still owner-stamped, only book_id-tagged so it surfaces
  //    under that book's library, EDIT-gated on the book). Quota-gated, not metered.
  /** Step 1: PROPOSE the adopt → a confirm token (+ a preview). No clone yet.
   *  Pass `opts.bookId` to tie the clone to that book: `opts.shared=false` (default) labels a
   *  PRIVATE per-user copy (target='book', model A); `opts.shared=true` adopts into the book's
   *  SHARED tier (target='book_shared', D-MOTIF-ADOPT-BOOK-COLLAB-TIER) — visible to + editable by
   *  the book's collaborators. Both require EDIT on the book (gated server-side). */
  async adoptEstimate(
    motifId: string, token: string, opts?: { bookId?: string | null; shared?: boolean },
  ): Promise<CostEstimate> {
    const bookArgs = opts?.bookId
      ? { target: opts.shared ? 'book_shared' : 'book', book_id: opts.bookId }
      : {};
    const res = await mcpExecute<_McpProposeResult>(
      'composition_motif_adopt',
      { args: { motif_id: motifId, ...bookArgs } },
      token,
    );
    return {
      confirm_token: res.confirm_token,
      descriptor: 'composition.motif_adopt',
      est_usd: 0, // adopt counts against the library quota; it is not LLM-metered
      est_tokens: 0,
      quota_remaining: null,
    };
  },
  /** Step 2: confirm the token (JWT-authed write) → the clone is created SYNCHRONOUSLY
   *  (no job); the effect returns the new motif_id, which we fetch as the full Motif. */
  async adoptConfirm(confirmToken: string, token: string): Promise<Motif> {
    const resp = await apiJson<{ outcome?: string; motif_id?: string } & Record<string, unknown>>(
      `${BASE}/actions/confirm${_qs({ token: confirmToken })}`,
      { method: 'POST', token }, // token in the QUERY; identity is the Bearer JWT
    );
    if (!resp.motif_id) throw new Error('adopt did not return a motif');
    return motifApi.get(resp.motif_id, token);
  },

  // ── Tier-W: mining (W8) — the self-enrichment flywheel ──────────────────────
  // composition_motif_mine spends LLM tokens (PrefixSpan over the corpus → LLM
  // abstraction → judge), so it is a 202+poll JOB: PROPOSE via the FE→MCP-tool bridge
  // (mint a confirm token + a $ estimate) → human confirms → poll the mine job → the
  // mined drafts (status='draft' motifs that then surface in the Drafts tab).
  /** Step 1 — PROPOSE composition_motif_mine → cost estimate + confirm_token. No spend. */
  async minePropose(
    args: {
      scope: 'book' | 'corpus'; bookId?: string | null; minSupport?: number;
      language?: string; modelRef: string; modelSource?: string;
    },
    token: string,
  ): Promise<CostEstimate> {
    const res = await mcpExecute<_McpProposeResult>(
      'composition_motif_mine',
      {
        args: {
          scope: args.scope,
          ...(args.scope === 'book' && args.bookId ? { book_id: args.bookId } : {}),
          ...(args.minSupport != null ? { min_support: args.minSupport } : {}),
          language: args.language ?? 'en',
          model_ref: args.modelRef,
          model_source: args.modelSource ?? 'user_model',
        },
      },
      token,
    );
    return {
      confirm_token: res.confirm_token,
      descriptor: 'composition.motif_mine',
      est_usd: res.estimate?.estimated_usd ?? 0,
      est_tokens: 0,
      quota_remaining: null,
    };
  },
  /** Step 2 — confirm the token → 202 + a mine job we poll to terminal; the job's
   *  result IS the MineResult (mined count + every candidate + degrade `reason`). */
  async mineConfirm(confirmToken: string, token: string): Promise<MineResult> {
    const resp = await apiJson<{ job_id?: string } & Record<string, unknown>>(
      `${BASE}/actions/confirm${_qs({ token: confirmToken })}`,
      { method: 'POST', token }, // token rides the QUERY; identity is the Bearer JWT
    );
    if (!resp.job_id) {
      return ((resp as { result?: MineResult }).result ?? (resp as unknown as MineResult));
    }
    // BE-7c — a motif-mine job is Work-LESS (project_id=NULL). Poll the OWNER-scoped
    // /motif-jobs/{id}, NOT getJob (/jobs/{id}), which gates on a Work that does not exist
    // and 404s forever after the user has paid for the mine.
    let job = await compositionApi.getMotifJob(resp.job_id, token);
    for (let i = 0; i < _POLL_MAX && (job.status === 'pending' || job.status === 'running'); i += 1) {
      await _sleep(_POLL_INTERVAL_MS);
      job = await compositionApi.getMotifJob(resp.job_id, token);
    }
    if (job.status === 'failed') {
      throw new Error((job.result as { error?: string } | null)?.error || 'mining failed');
    }
    if (job.status !== 'completed') throw new Error('mining did not complete in time');
    return job.result as MineResult;
  },
  /** Promote a mined draft into the active library (status draft → active). Reuses the
   *  owner-only PATCH (If-Match optimistic lock); discard is `archive`. */
  promote(motifId: string, expectedVersion: number, token: string): Promise<Motif> {
    return motifApi.patch(motifId, { status: 'active' }, expectedVersion, token);
  },

  // ── publish sync (W11) — upstream-diff + apply-merge ─────────────────────────
  /** The per-field diff of an adopted motif vs its current upstream (3-way when a base
   *  snapshot exists, else 2-way). 404/409/410 when not the caller's resolvable clone. */
  upstreamDiff(motifId: string, token: string): Promise<SyncDiff> {
    return apiJson<SyncDiff>(`${BASE}/motifs/${motifId}/upstream-diff`, { token });
  },
  /** Apply the chosen merge: `accept` = the upstream-changed fields to TAKE ([] = keep all
   *  local, just re-pin). Atomic content-merge + re-pin (+ 3-way re-baseline). */
  sync(motifId: string, accept: string[], token: string): Promise<SyncResult> {
    return apiJson<SyncResult>(`${BASE}/motifs/${motifId}/sync`, {
      method: 'POST', body: JSON.stringify({ accept }), token,
    });
  },

  // ── conformance trace (W5) ─────────────────────────────────────────────────
  conformance(projectId: string, chapterId: string, token: string): Promise<ChapterConformance> {
    return apiJson<ChapterConformance>(
      `${BASE}/works/${projectId}/conformance${_qs({ scope: 'chapter', chapter_id: chapterId })}`,
      { token },
    );
  },
  /** Coarse arc-conformance (D-W10-ARC-CONFORMANCE) — the structural diff of the durable
   *  SPEC arc (scope=arc) vs the realized prose. `arcId` is a **`structure_node.id`** (spec 23
   *  BA4 retarget), NOT an arc_template id — M-BUG-4: the wire arg is `arc_id`, and sending
   *  `arc_template_id` made FastAPI drop it → arc_id=None → 422 ARC_ID_REQUIRED on every call. */
  arcConformance(projectId: string, arcId: string, token: string, deep = false, modelRef?: string | null): Promise<ArcConformance> {
    return apiJson<ArcConformance>(
      `${BASE}/works/${projectId}/conformance${_qs({
        scope: 'arc', arc_id: arcId,
        ...(deep ? { deep: 'true' } : {}),
        // model_ref opts into thread-tagging (deep thread-progression); omit ⇒ pacing + existing tags.
        ...(deep && modelRef ? { model_ref: modelRef, model_source: 'user_model' } : {}),
      })}`,
      { token },
    );
  },
  /** Chapter conformance RE-RUN (Tier-W + BYOK) — spec 33 §3.4: the run goes through the
   *  generic MCP spine (composition_conformance_run), NOT the deleted bespoke
   *  /actions/conformance_run/* REST twins. PROPOSE mints a confirm_token + estimate (no spend);
   *  mirror of arcConformanceRunPropose. */
  async chapterConformanceRunPropose(
    args: { projectId: string; chapterId: string; modelRef: string; modelSource?: string },
    token: string,
  ): Promise<CostEstimate> {
    const res = await mcpExecute<_McpProposeResult>('composition_conformance_run', {
      args: {
        project_id: args.projectId, scope: 'chapter', chapter_id: args.chapterId,
        model_ref: args.modelRef, model_source: args.modelSource ?? 'user_model',
      },
    }, token);
    return {
      confirm_token: res.confirm_token, descriptor: 'composition.conformance_run',
      est_usd: res.estimate?.estimated_usd ?? 0, est_tokens: 0, quota_remaining: null,
    };
  },
  /** Confirm the re-run token (the JWT-authed write path) → poll the job to terminal. The
   *  caller invalidates the conformance query on success, so the GET re-fetches the fresh trace
   *  (no result-shape parsing needed). */
  async chapterConformanceRunConfirm(confirmToken: string, token: string): Promise<void> {
    const resp = await apiJson<{ job_id?: string } & Record<string, unknown>>(
      `${BASE}/actions/confirm${_qs({ token: confirmToken })}`, { method: 'POST', token },
    );
    if (!resp.job_id) return;
    let job = await compositionApi.getJob(resp.job_id, token);
    for (let i = 0; i < _POLL_MAX && (job.status === 'pending' || job.status === 'running'); i += 1) {
      await _sleep(_POLL_INTERVAL_MS);
      job = await compositionApi.getJob(resp.job_id, token);
    }
    if (job.status === 'failed') throw new Error((job.result as { error?: string } | null)?.error || 'conformance run failed');
    if (job.status !== 'completed') throw new Error('conformance run did not complete in time');
  },

  // ── DEEP arc-conformance JOB (D-W10-ARC-CONFORMANCE-DEEP-FE) ─────────────────
  // The deep arc overlay re-tags the book's prose with ~120 LLM calls, so it is a
  // Tier-W 202+poll JOB (never a synchronous GET — that would time out on a real
  // book). PROPOSE mints a confirm token via the FE→MCP-tool bridge (the agentic
  // mint is an MCP tool-call, per MCP-first), the human confirms (the existing
  // JWT-authed /actions/confirm), and we poll the job to its deep arc report.
  /** Step 1 — PROPOSE `composition_conformance_run` (scope=arc) → a cost estimate +
   *  confirm_token. No spend yet (the worker runs only after confirm). */
  async arcConformanceRunPropose(
    args: { projectId: string; arcId: string; modelRef: string; modelSource?: string },
    token: string,
  ): Promise<CostEstimate> {
    const res = await mcpExecute<_McpProposeResult>(
      'composition_conformance_run',
      // The MCP tool takes a single pydantic `args` parameter, so FastMCP nests the
      // fields under `args` (verified live — a flat body fails arg validation).
      // M-BUG-4: the tool's _ConformanceRunArgs is ForbidExtra with `arc_id` (a structure_node.id)
      // and NO `arc_template_id` — sending the latter 422'd every deep-arc run.
      {
        args: {
          project_id: args.projectId,
          scope: 'arc',
          arc_id: args.arcId,
          model_ref: args.modelRef,
          model_source: args.modelSource ?? 'user_model',
        },
      },
      token,
    );
    // The MCP propose envelope estimate is `{estimated_usd, currency, basis}` — map
    // it onto the FE CostEstimate (token count + quota aren't part of this estimate).
    return {
      confirm_token: res.confirm_token,
      descriptor: 'composition.conformance_run',
      est_usd: res.estimate?.estimated_usd ?? 0,
      est_tokens: 0,
      quota_remaining: null,
    };
  },
  /** Step 2 — confirm the token (the JWT-authed write path) → 202 + a job we poll to
   *  terminal; the job's result IS the deep arc report (an `ArcConformance` with
   *  `.deep` populated). */
  async arcConformanceRunConfirm(confirmToken: string, token: string): Promise<ArcConformance> {
    const resp = await apiJson<{ job_id?: string } & Record<string, unknown>>(
      `${BASE}/actions/confirm${_qs({ token: confirmToken })}`,
      { method: 'POST', token }, // token rides the QUERY; identity is the Bearer JWT
    );
    if (!resp.job_id) {
      // Inline / already-consumed reply — return its result verbatim (replay-safe).
      return ((resp as { result?: ArcConformance }).result ?? (resp as unknown as ArcConformance));
    }
    let job = await compositionApi.getJob(resp.job_id, token);
    for (let i = 0; i < _POLL_MAX && (job.status === 'pending' || job.status === 'running'); i += 1) {
      await _sleep(_POLL_INTERVAL_MS);
      job = await compositionApi.getJob(resp.job_id, token);
    }
    if (job.status === 'failed') {
      throw new Error((job.result as { error?: string } | null)?.error || 'conformance run failed');
    }
    if (job.status !== 'completed') {
      throw new Error('conformance run did not complete in time');
    }
    return job.result as ArcConformance;
  },
  /** Regenerate one scene — spec 33 §5.1: reuse the EXISTING scene-generate route
   *  (composition_generate's REST twin, `outline_node_id`), NOT the removed
   *  regenerate-to-beat endpoint (BE-5 was never built; §5.1). The bound motif now steers
   *  generation through the packer's gather_motif lens (BE-M2), so a plain regenerate honours
   *  the beat. */
  regenerateScene(projectId: string, outlineNodeId: string, token: string): Promise<{ job_id?: string }> {
    return apiJson(`${BASE}/works/${projectId}/generate`, {
      method: 'POST', body: JSON.stringify({ outline_node_id: outlineNodeId }), token,
    });
  },
};

// The MCP propose tool returns a confirm token + a cost estimate envelope. Shape
// mirrors composition_conformance_run's return (server.py): a flat object whose
// `estimate` is `{estimated_usd, currency, basis}`.
type _McpProposeResult = {
  confirm_token: string;
  descriptor?: string;
  estimate?: { estimated_usd?: number; currency?: string; basis?: string };
};

// The Tier-W actions route answers a 202 `{ job_id, status }` (the spend runs in a
// worker) OR an inline already-consumed result. We poll to terminal via the
// existing composition job machinery (compositionApi.getJob). A "token already
// consumed" reply is replay-safe success (idempotency — §4.5).
const _POLL_INTERVAL_MS = 1500;
const _POLL_MAX = 200;
const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A QuotaError thrown by the api carries `code: 'quota_exceeded'` (the legacy estimate
 *  shape) OR the composition confirm-effect 402 shape `{code:'action_error',
 *  reason:'quota_exhausted'}` (adopt mints via the bridge, so the quota ceiling now
 *  bites at confirm, not propose). apiJson attaches the parsed body. */
export function isQuotaError(err: unknown): err is { body: { resource: string; limit: number; used: number } } {
  const e = err as { code?: string; body?: { code?: string; reason?: string } } | null;
  return (
    !!e &&
    (e.code === 'quota_exceeded' ||
      e.body?.code === 'quota_exceeded' ||
      e.body?.reason === 'quota_exhausted')
  );
}

export { type MotifTier };
