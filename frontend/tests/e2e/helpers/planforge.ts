// PlanForge (S3) e2e helpers — the API surface a Pass Rail spec drives to set up state, plus the
// gemma model resolver. Mirrors helpers/api.ts (auth() + gateway request). LLM steps (propose,
// run_pass, autofix) are model-gated by the caller via listChatModels.
import type { APIRequestContext } from '@playwright/test';

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });
const BASE = '/v1/composition';

export interface PlanPass {
  pass_id: string; checkpoint: string; status: string; decision: string;
  fresh: boolean; blockers: string[]; artifact_id: string | null;
}
export interface PlanLedger {
  compiled: boolean; passes: PlanPass[]; pass_cursor: number; blocked_at: string | null;
}

/** The test account's local gemma-4-26B-A4B QAT ($0), if present — the S3 LLM smokes' model. */
/** The local gemma chat model, or null.
 *
 * 🔴 This asked `/v1/ai/models?capability=chat`, which answers **404 Not Found**. So it returned
 * null unconditionally and BOTH plan-forge specs skipped permanently with
 * "needs the local gemma model" -- a reason that reads like a missing model and was a dead
 * endpoint. A skip is unanswered, and this one had been unanswered silently.
 *
 * The live route is the model registry, which returns `{ items: [...] }` rather than a bare
 * array. INACTIVE models are excluded: an inactive model is a ref that resolves to nothing, and
 * handing one to a run produces LLM_MODEL_NOT_FOUND on every batch (the A6 lesson).
 */
export async function findGemma(request: APIRequestContext, token: string): Promise<string | null> {
  const r = await request.get('/v1/model-registry/user-models?capability=chat', auth(token));
  if (!r.ok()) return null;
  const body = (await r.json()) as { items?: UserModelRow[] } | UserModelRow[];
  const models: UserModelRow[] = Array.isArray(body) ? body : (body.items ?? []);
  const g = models
    .filter((m) => m.is_active !== false)
    .find((m) => /gemma-4.*26b.*qat/i.test(`${m.alias ?? ''} ${m.provider_model_name ?? ''}`));
  return g?.user_model_id ?? null;
}

type UserModelRow = {
  user_model_id: string;
  alias?: string;
  provider_model_name?: string;
  is_active?: boolean;
};

export async function createPlanRun(
  request: APIRequestContext, token: string, bookId: string,
  body: {
    source_markdown: string; mode: 'rules' | 'llm'; model_ref?: string; genre_tags?: string[];
    // PROPOSE-BLIND — ask the proposer to continue the book (effective only if the deploy ceiling allows).
    ground_on_existing?: boolean; force?: boolean;
  },
): Promise<string> {
  const r = await request.post(`${BASE}/books/${bookId}/plan/runs`, { ...auth(token), data: body });
  if (!r.ok() && r.status() !== 202) throw new Error(`createPlanRun ${r.status()}: ${await r.text()}`);
  const d = await r.json();
  return d.run_id ?? d.id;
}

async function poll<T>(fn: () => Promise<T>, done: (v: T) => boolean, tries = 45, ms = 4000): Promise<T> {
  let v = await fn();
  for (let i = 0; i < tries && !done(v); i++) { await new Promise((r) => setTimeout(r, ms)); v = await fn(); }
  return v;
}

/** The plan-run read model the specs assert on. Only the fields they read are named; the
 *  server returns more. */
export interface PlanRun {
  status: string;
  job_status: string | null;
  arcs: Array<{ id: string }>;
  grounded_on?: { fingerprint: string; arc_titles: string[] } | null;
}

export async function getRun(request: APIRequestContext, token: string, bookId: string, runId: string): Promise<PlanRun> {
  const r = await request.get(`${BASE}/books/${bookId}/plan/runs/${runId}`, auth(token));
  return r.json();
}

export async function waitProposed(request: APIRequestContext, token: string, bookId: string, runId: string) {
  return poll(
    () => getRun(request, token, bookId, runId),
    (d: PlanRun) =>
      // 'compiled' — a rules-mode propose with autocompile ON materialises the arcs inline and lands
      // here, not at 'proposed'; accept it as a terminal state so grounded rules runs don't hang.
      ['proposed', 'validated', 'checkpoint', 'compiled', 'failed'].includes(d.status) &&
      [null, 'completed', 'failed'].includes(d.job_status),
  );
}

export async function compileArc(
  request: APIRequestContext, token: string, bookId: string, runId: string, arcId: string,
) {
  const r = await request.post(`${BASE}/books/${bookId}/plan/runs/${runId}/compile`, {
    ...auth(token), data: { arc_id: arcId },
  });
  return { status: r.status(), body: r.ok() ? await r.json() : await r.text() };
}

export async function getPasses(
  request: APIRequestContext, token: string, bookId: string, runId: string,
): Promise<PlanLedger> {
  const r = await request.get(`${BASE}/books/${bookId}/plan/runs/${runId}/passes`, auth(token));
  return r.json();
}

export async function runPass(
  request: APIRequestContext, token: string, bookId: string, runId: string, passId: string, modelRef: string,
) {
  await request.post(`${BASE}/books/${bookId}/plan/runs/${runId}/passes/${passId}/run`, {
    ...auth(token), data: { model_ref: modelRef },
  });
  return poll(
    () => getPasses(request, token, bookId, runId),
    (l) => { const p = l.passes.find((x) => x.pass_id === passId); return !!p && ['completed', 'failed'].includes(p.status); },
  );
}
