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
import { compositionApi } from '../api';
import type { GenerationJob } from '../types';
import type {
  ArcConformance, CatalogList, ChapterConformance, CostEstimate, Motif, MotifCreateArgs,
  MotifPatchArgs, MotifTier,
} from './types';

const BASE = '/v1/composition';

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

  // ── Tier-W: adopt = clone (R2.8 confirm-token). mint → confirm → poll ───────
  /** Step 1: mint a cost estimate + confirm_token for adopting `motifId` into the
   *  target (the User library, or a book). No spend yet. */
  adoptEstimate(
    motifId: string,
    target: { kind: 'user' } | { kind: 'book'; book_id: string },
    token: string,
  ): Promise<CostEstimate> {
    return apiJson<CostEstimate>(`${BASE}/actions/motif_adopt/estimate`, {
      method: 'POST', body: JSON.stringify({ motif_id: motifId, target }), token,
    });
  },
  /** Step 2: confirm the minted token → 202 + a job we poll to terminal. Replay-
   *  safe: a consumed token comes back already-done (treated as success). */
  async adoptConfirm(confirmToken: string, token: string): Promise<Motif> {
    const resp = await apiJson<{ job_id?: string; status?: string; motif?: Motif } & Record<string, unknown>>(
      `${BASE}/actions/motif_adopt/confirm`,
      { method: 'POST', body: JSON.stringify({ confirm_token: confirmToken }), token },
    );
    const job = await _resolveActionJob(resp, token);
    return (job.result as { motif: Motif }).motif;
  },

  // ── conformance trace (W5) ─────────────────────────────────────────────────
  conformance(projectId: string, chapterId: string, token: string): Promise<ChapterConformance> {
    return apiJson<ChapterConformance>(
      `${BASE}/works/${projectId}/conformance${_qs({ scope: 'chapter', chapter_id: chapterId })}`,
      { token },
    );
  },
  /** Coarse arc-conformance (D-W10-ARC-CONFORMANCE) — the structural diff of the
   *  materialized bindings vs the arc template (scope=arc). */
  arcConformance(projectId: string, arcTemplateId: string, token: string, deep = false): Promise<ArcConformance> {
    return apiJson<ArcConformance>(
      `${BASE}/works/${projectId}/conformance${_qs({ scope: 'arc', arc_template_id: arcTemplateId, ...(deep ? { deep: 'true' } : {}) })}`,
      { token },
    );
  },
  conformanceRunEstimate(projectId: string, chapterId: string, token: string): Promise<CostEstimate> {
    return apiJson<CostEstimate>(`${BASE}/actions/conformance_run/estimate`, {
      method: 'POST', body: JSON.stringify({ project_id: projectId, chapter_id: chapterId }), token,
    });
  },
  async conformanceRunConfirm(confirmToken: string, token: string): Promise<ChapterConformance> {
    const resp = await apiJson<{ job_id?: string; status?: string } & Record<string, unknown>>(
      `${BASE}/actions/conformance_run/confirm`,
      { method: 'POST', body: JSON.stringify({ confirm_token: confirmToken }), token },
    );
    const job = await _resolveActionJob(resp, token);
    return (job.result as { conformance: ChapterConformance }).conformance;
  },
  /** Regenerate one scene within its bound beat (reuses the scene-regenerate path). */
  regenerateToBeat(projectId: string, nodeId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/works/${projectId}/scenes/${nodeId}/regenerate-to-beat`, {
      method: 'POST', token,
    });
  },
};

// The Tier-W actions route answers a 202 `{ job_id, status }` (the spend runs in a
// worker) OR an inline already-consumed result. We poll to terminal via the
// existing composition job machinery (compositionApi.getJob). A "token already
// consumed" reply is replay-safe success (idempotency — §4.5).
const _POLL_INTERVAL_MS = 1500;
const _POLL_MAX = 200;
const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function _resolveActionJob(
  resp: { job_id?: string; status?: string } & Record<string, unknown>,
  token: string,
): Promise<GenerationJob> {
  // Inline (already-consumed / synchronous) — the result is on the response.
  if (!resp.job_id) {
    return resp as unknown as GenerationJob;
  }
  if (resp.status !== 'pending' && resp.status !== 'running') {
    return resp as unknown as GenerationJob;
  }
  let job = await compositionApi.getJob(resp.job_id, token);
  for (let i = 0; i < _POLL_MAX && (job.status === 'pending' || job.status === 'running'); i += 1) {
    await _sleep(_POLL_INTERVAL_MS);
    job = await compositionApi.getJob(resp.job_id, token);
  }
  if (job.status === 'failed') {
    throw new Error((job.result as { error?: string } | null)?.error || 'action failed');
  }
  if (job.status !== 'completed') {
    throw new Error('action did not complete in time');
  }
  return job;
}

/** A QuotaError thrown by the api carries `code: 'quota_exceeded'` on the error
 *  body (apiJson attaches the parsed body). The hooks read it for the explainer. */
export function isQuotaError(err: unknown): err is { body: { resource: string; limit: number; used: number } } {
  const e = err as { code?: string; body?: { code?: string } } | null;
  return !!e && (e.code === 'quota_exceeded' || e.body?.code === 'quota_exceeded');
}

export { type MotifTier };
