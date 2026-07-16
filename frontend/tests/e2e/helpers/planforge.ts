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
export async function findGemma(request: APIRequestContext, token: string): Promise<string | null> {
  const r = await request.get('/v1/ai/models?capability=chat', auth(token));
  if (!r.ok()) return null;
  const models = (await r.json()) as Array<{ user_model_id: string; alias?: string; provider_model_name?: string }>;
  const g = models.find((m) => /gemma-4.*26b.*qat/i.test(`${m.alias} ${m.provider_model_name}`));
  return g?.user_model_id ?? null;
}

export async function createPlanRun(
  request: APIRequestContext, token: string, bookId: string,
  body: { source_markdown: string; mode: 'rules' | 'llm'; model_ref?: string; genre_tags?: string[] },
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

export async function getRun(request: APIRequestContext, token: string, bookId: string, runId: string) {
  const r = await request.get(`${BASE}/books/${bookId}/plan/runs/${runId}`, auth(token));
  return r.json();
}

export async function waitProposed(request: APIRequestContext, token: string, bookId: string, runId: string) {
  return poll(
    () => getRun(request, token, bookId, runId),
    (d: { status: string; job_status: string | null }) =>
      ['proposed', 'validated', 'checkpoint', 'failed'].includes(d.status) &&
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
