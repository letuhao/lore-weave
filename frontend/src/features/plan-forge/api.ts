// PlanForge (M5) — gateway calls. Relative /v1 rides the Vite proxy → gateway (dev :3123) /
// nginx (prod). Same `apiJson` client + `token` convention as compositionApi. NO backend or
// contract changes here — this is the FE consumer of the composition-service /plan surface.
import { apiJson } from '@/api';
import type {
  BootstrapProposal,
  CompilePlanBody,
  CreatePlanRunBody,
  InterpretPlanBody,
  PlanCompileResult,
  PlanInterpretation,
  PlanRunAck,
  PlanRunDetail,
  PlanRunListPage,
  PlanSelfCheck,
  PlanValidateReport,
  RefinePlanBody,
} from './types';

const BASE = '/v1/composition';

// POST /runs answers 201 (rules → full detail) OR 202 (llm → an ack {run_id, job_id, status}).
// We surface the raw union so the hook can normalize both to a run handle (it re-fetches the
// detail after an llm ack anyway, since the ack isn't a full detail).
export type CreatePlanRunResponse = PlanRunDetail | PlanRunAck;

// A 202 acknowledgement carries `run_id` + `job_id` but NOT a full-detail `id`. Widened to accept
// any of the create/refine/compile response unions (all of which may be an ack or a full result).
function isAck(r: unknown): r is PlanRunAck {
  const o = r as { run_id?: unknown; id?: unknown };
  return o != null && o.run_id !== undefined && o.id === undefined;
}

export const planForgeApi = {
  createRun(bookId: string, body: CreatePlanRunBody, token: string): Promise<CreatePlanRunResponse> {
    return apiJson<CreatePlanRunResponse>(`${BASE}/books/${bookId}/plan/runs`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  listRuns(
    bookId: string, token: string, opts: { limit?: number; cursor?: string | null } = {},
  ): Promise<PlanRunListPage> {
    const p = new URLSearchParams();
    if (opts.limit) p.set('limit', String(opts.limit));
    if (opts.cursor) p.set('cursor', opts.cursor);
    const qs = p.toString();
    return apiJson<PlanRunListPage>(`${BASE}/books/${bookId}/plan/runs${qs ? `?${qs}` : ''}`, { token });
  },
  getRun(bookId: string, runId: string, token: string): Promise<PlanRunDetail> {
    return apiJson<PlanRunDetail>(`${BASE}/books/${bookId}/plan/runs/${runId}`, { token });
  },
  // BE-3 — one artifact's content (read-only). The Pass Rail loads this to render what a
  // blocking checkpoint (cast/beats) is asking the human to approve.
  getArtifact(
    bookId: string, runId: string, artifactId: string, token: string,
  ): Promise<import('./types').PlanArtifactDetail> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/artifacts/${artifactId}`, { token });
  },
  patchNovelSystemSpec(
    bookId: string, runId: string, spec: Record<string, unknown>, token: string,
  ): Promise<PlanRunDetail> {
    return apiJson<PlanRunDetail>(`${BASE}/books/${bookId}/plan/runs/${runId}/novel-system-spec`, {
      method: 'PATCH', body: JSON.stringify(spec), token,
    });
  },
  validate(bookId: string, runId: string, token: string): Promise<PlanValidateReport> {
    return apiJson<PlanValidateReport>(`${BASE}/books/${bookId}/plan/runs/${runId}/validate`, {
      method: 'POST', token,
    });
  },
  selfCheck(bookId: string, runId: string, token: string): Promise<PlanSelfCheck> {
    return apiJson<PlanSelfCheck>(`${BASE}/books/${bookId}/plan/runs/${runId}/self-check`, {
      method: 'POST', token,
    });
  },
  // 202 {run_id, job_id, status} when the refine runs on the worker; else the applied result.
  refine(
    bookId: string, runId: string, body: RefinePlanBody, token: string,
  ): Promise<import('./types').PlanRefineResult | PlanRunAck> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/refine`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  interpret(
    bookId: string, runId: string, body: InterpretPlanBody, token: string,
  ): Promise<PlanInterpretation> {
    return apiJson<PlanInterpretation>(`${BASE}/books/${bookId}/plan/runs/${runId}/interpret`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // BE-2 — the bounded self-check→refine loop (plan_handoff_autofix). 200 {rounds, run} on the
  // worker-off path; 202 {rounds, run} when a round enqueued. The Repair strip renders `rounds`.
  autofix(
    bookId: string, runId: string, body: { model_ref?: string; max_rounds?: number }, token: string,
  ): Promise<import('./types').PlanAutofixResult> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/autofix`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // 202 {run_id, job_id, status} when the pipeline runs on the worker; else the compile package.
  compile(
    bookId: string, runId: string, body: CompilePlanBody, token: string,
  ): Promise<PlanCompileResult | PlanRunAck> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/compile`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // ── 27 V2 · the 7-pass compiler rail ──────────────────────────────────────────────
  // GET the derived pass ledger (per-pass status/decision/fresh + pass_cursor + blocked_at).
  passStatus(
    bookId: string, runId: string, token: string,
  ): Promise<import('./types').PlanPassLedger> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/passes`, { token });
  },
  // Run ONE compiler pass. 202 {job_id, …} + the derived pass view; 409 UPSTREAM_STALE when an
  // upstream is stale/unaccepted (blockers ride along). paid=true — spends the author's LLM budget.
  runPass(
    bookId: string, runId: string, passId: string,
    body: import('./types').RunPassBody, token: string,
  ): Promise<unknown> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/passes/${passId}/run`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // POST /link — (re-)link a compiled plan into the book's spec/outline tree. Idempotent; never
  // overwrites a node a human edited. 'skeleton' = arcs + chapters; 'scene_plan' = the scenes.
  relink(
    bookId: string, runId: string, target: 'skeleton' | 'scene_plan', token: string,
  ): Promise<unknown> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/link`, {
      method: 'POST', body: JSON.stringify({ target }), token,
    });
  },
  // POST /checkpoint — approve/hold a pass (or the spec checkpoint, omit pass_id). `edits`
  // deep-merges into the pass artifact (a NEW artifact → downstream stales by derivation).
  reviewCheckpoint(
    bookId: string, runId: string,
    body: { approved: boolean; pass_id?: string; edits?: Record<string, unknown> },
    token: string,
  ): Promise<import('./types').PlanPassLedger> {
    return apiJson(`${BASE}/books/${bookId}/plan/runs/${runId}/checkpoint`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },

  // Auto-bootstrap gate (M4) — propose runs the diff ONCE; approve/reject/apply never
  // re-propose. See docs/specs/2026-07-06-planforge-auto-bootstrap.md §6.
  bootstrapPropose(bookId: string, runId: string, token: string): Promise<BootstrapProposal> {
    return apiJson<BootstrapProposal>(`${BASE}/books/${bookId}/plan/runs/${runId}/bootstrap/propose`, {
      method: 'POST', token,
    });
  },
  bootstrapGet(bookId: string, proposalId: string, token: string): Promise<BootstrapProposal> {
    return apiJson<BootstrapProposal>(`${BASE}/books/${bookId}/plan/bootstrap/${proposalId}`, { token });
  },
  bootstrapApprove(bookId: string, proposalId: string, token: string): Promise<BootstrapProposal> {
    return apiJson<BootstrapProposal>(`${BASE}/books/${bookId}/plan/bootstrap/${proposalId}/approve`, {
      method: 'POST', token,
    });
  },
  bootstrapReject(bookId: string, proposalId: string, token: string): Promise<BootstrapProposal> {
    return apiJson<BootstrapProposal>(`${BASE}/books/${bookId}/plan/bootstrap/${proposalId}/reject`, {
      method: 'POST', token,
    });
  },
  bootstrapApply(bookId: string, proposalId: string, token: string): Promise<BootstrapProposal> {
    return apiJson<BootstrapProposal>(`${BASE}/books/${bookId}/plan/bootstrap/${proposalId}/apply`, {
      method: 'POST', token,
    });
  },
};

export { isAck };
