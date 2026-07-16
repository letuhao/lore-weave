// 34 §4.3 拆文 (Import & Deconstruct) — the API layer. Turn a reference story into a reusable arc
// template. Two halves: import-source CRUD (the raw text, private by construction — no visibility
// column), and the PRICED deconstruct, which rides the GENERIC cost-gate spine (AT-5): PROPOSE via
// the FE→MCP bridge (mint a confirm token + $ estimate, NO spend) → human confirms → poll the
// WORK-LESS job (AT-11: GET /motif-jobs/{id}, never /jobs/{id} which gates on a Work it lacks).
import { apiJson } from '../../../api';
import { mcpExecute } from '../../../mcpBridge';
import { compositionApi } from '../api';
import type { CostEstimate } from '../motif/types';

const BASE = '/v1/composition';

export interface ImportSource {
  id: string;
  title: string;
  created_at: string;
  content_length?: number;
}

/** The MCP `_ArcImportArgs` is ForbidExtra — send EXACTLY these fields (spec 34 §2). */
export interface DeconstructArgs {
  importSourceId: string;
  arcHint?: string;
  useWeb?: boolean;
  language?: string;
  modelRef: string;
  modelSource?: string;
}

const _POLL_MAX = 120;
const _POLL_INTERVAL_MS = 2000;
const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface _McpProposeResult {
  confirm_token: string;
  estimate?: { estimated_usd?: number } | null;
}

export const arcImportApi = {
  listSources(token: string): Promise<{ import_sources: ImportSource[] }> {
    return apiJson(`${BASE}/import-sources`, { token });
  },
  /** content is capped at 20 000 chars server-side (StringConstraints) — the FE counts + blocks
   *  BEFORE submit so we never 422 an essay. */
  createSource(body: { content: string; title: string }, token: string): Promise<ImportSource> {
    return apiJson(`${BASE}/import-sources`, { method: 'POST', token, body: JSON.stringify(body) });
  },
  /** hard delete — there is no restore; the caller must say so. */
  async deleteSource(id: string, token: string): Promise<void> {
    await apiJson(`${BASE}/import-sources/${id}`, { method: 'DELETE', token });
  },

  /** Step 1 — PROPOSE composition_arc_import_analyze → {confirm_token, $ estimate}. No spend. The
   *  MCP tool takes a single `args` model, so the bridge body MUST nest the fields under `args`. */
  async deconstructPropose(a: DeconstructArgs, token: string): Promise<CostEstimate> {
    const res = await mcpExecute<_McpProposeResult>(
      'composition_arc_import_analyze',
      {
        args: {
          import_source_id: a.importSourceId,
          use_web: a.useWeb ?? false,
          ...(a.arcHint ? { arc_hint: a.arcHint } : {}),
          language: a.language ?? 'en',
          model_ref: a.modelRef,
          model_source: a.modelSource ?? 'user_model',
        },
      },
      token,
    );
    return {
      confirm_token: res.confirm_token,
      descriptor: 'composition.arc_import',
      est_usd: res.estimate?.estimated_usd ?? 0,
      est_tokens: 0,
      quota_remaining: null,
    };
  },

  /** Step 2 — confirm the token → {job_id} → poll the WORK-LESS job to terminal → the new template.
   *  ⚠ Before W0-BE1 the confirm itself 500'd; a catch-into-spinner is how that hid. Surface the
   *  confirm's own failure AND the job's `failed` result verbatim — never a spinner-forever. */
  async deconstructConfirm(confirmToken: string, token: string): Promise<Record<string, unknown>> {
    const resp = await apiJson<{ job_id?: string } & Record<string, unknown>>(
      `${BASE}/actions/confirm?token=${encodeURIComponent(confirmToken)}`,
      { method: 'POST', token }, // token in the QUERY; identity is the Bearer JWT
    );
    if (!resp.job_id) {
      // no job id at all ⇒ the confirm itself failed (or replayed) — do not pretend success.
      throw new Error((resp as { error?: string }).error || 'deconstruct was not accepted');
    }
    let job = await compositionApi.getMotifJob(resp.job_id, token);
    for (let i = 0; i < _POLL_MAX && (job.status === 'pending' || job.status === 'running'); i += 1) {
      await _sleep(_POLL_INTERVAL_MS);
      job = await compositionApi.getMotifJob(resp.job_id, token);
    }
    if (job.status === 'failed') {
      throw new Error((job.result as { error?: string } | null)?.error || 'deconstruct failed');
    }
    if (job.status !== 'completed') throw new Error('deconstruct did not complete in time');
    return (job.result as Record<string, unknown>) ?? {};
  },
};
