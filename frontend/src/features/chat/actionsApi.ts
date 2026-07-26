// MCP fan-out (C-CONFIRM / C-PROPOSE) — the generic, domain-parameterised action
// API the confirm card + record-diff card call. The `domain` (glossary|book|
// translation|settings|composition|…) selects the committing endpoint; the
// shapes are uniform across providers (each provider slice wires its own
// /v1/<domain>/actions/{preview,confirm} pair using the kit's mint/verify).
//
// Glossary already ships these routes today; this client is the single FE caller
// so a new provider needs zero FE changes — only an `AI_GATEWAY_PROVIDERS` entry
// + its own routes.

import { apiJson } from '@/api';

export interface ActionPreviewRow {
  label: string;
  value: string;
  note?: string;
  /** Set for execute_plan previews (one row per plan op). A row with `destructive`
   *  renders an opt-in enable toggle keyed by `op_id`; the checked ids are sent as
   *  `enabled_ops` at confirm (the executor skips a destructive op unless enabled). */
  op_id?: string;
  destructive?: boolean;
}

export interface ActionPreview {
  descriptor: string;
  title: string;
  preview_rows: ActionPreviewRow[] | null;
  destructive: boolean;
}

/** H-J / H14 re-price-on-execute — the structured detail a priced confirm route
 *  returns on a >×1.25 (+$0.50 abs) cost drift since the token was minted. The BE
 *  emits HTTP 409 `TRANSL_REPRICE_REQUIRED` with this detail (FastAPI wraps it under
 *  `{detail}`); the card surfaces the NEW number so the human re-confirms against the
 *  real, higher cost instead of silently overspending. The FE NEVER computes the
 *  threshold — it only reacts to the BE's 409 (D-TRANSL-REPRICE-THRESHOLD-DRIFT). */
export interface RepriceDetail {
  code?: string;
  message?: string;
  status?: string;
  confirmed_cost_usd?: number | null;
  actual_cost_usd?: number | null;
  estimate?: { cost_usd?: number | null } & Record<string, unknown>;
}

/** Detect + extract a re-price 409 out of a thrown `apiJson` error. Returns the
 *  detail when the error is a 409 whose body marks `reprice_required`
 *  (`status==='reprice_required'` or `code==='TRANSL_REPRICE_REQUIRED'`), else null.
 *  FastAPI nests the HTTPException detail under `body.detail`; a non-FastAPI emitter
 *  (or the headless edge replay) may put it at `body` directly — accept both. */
export function parseRepriceError(err: unknown): RepriceDetail | null {
  const e = err as { status?: number; body?: unknown };
  if (e?.status !== 409 || e.body == null || typeof e.body !== 'object') return null;
  const body = e.body as Record<string, unknown>;
  const raw = (body.detail && typeof body.detail === 'object' ? body.detail : body) as RepriceDetail;
  const isReprice =
    raw.status === 'reprice_required' || raw.code === 'TRANSL_REPRICE_REQUIRED';
  return isReprice ? raw : null;
}

/** Per-child outcome from a coalesced confirm-batch (#27/#29/#30). */
export interface BatchChildOutcome {
  descriptor: string;
  outcome: 'applied' | 'skipped' | 'failed';
  status: number;
  detail?: string;
}

/** The aggregate result of POST /v1/<domain>/actions/confirm-batch. */
export interface BatchConfirmResult {
  applied: number;
  skipped: number;
  failed: number;
  children: BatchChildOutcome[];
}

/** Domains that ship the atomic /actions/confirm-batch endpoint (one call commits all
 *  child tokens). Other domains are committed by the card looping single confirmAction —
 *  so the coalesced card works for EVERY domain, with the batch endpoint as a fast-path.
 *  Add a domain here once its service grows a confirm-batch route. */
export const BATCH_CONFIRM_DOMAINS = new Set<string>(['glossary']);

/** One field change in a server-built diff card (e.g. book_update_details / descriptor
 *  `book.meta`), rendered old→new by ConfirmActionCard. */
export interface RecordEditChange {
  field_label?: string;
  old_value?: string;
  new_value?: string;
  /** which sub-resource this targets (e.g. "short_description", "attribute") */
  target?: string;
  /** id of the targeted sub-resource when `target` needs one */
  target_ref?: string;
}

/** Build the relative `/v1/<domain>/actions/...` base. Domain is a fixed enum on
 *  the agent side; we still guard against an empty value defensively. */
function actionsBase(domain: string): string {
  return `/v1/${encodeURIComponent(domain)}/actions`;
}

export const actionsApi = {
  /** C-CONFIRM preview: non-consuming current-state render for the confirm card.
   *  GET with the token as a query param (uniform across providers). */
  previewAction(domain: string, confirmToken: string, token: string): Promise<ActionPreview> {
    return apiJson<ActionPreview>(
      `${actionsBase(domain)}/preview?token=${encodeURIComponent(confirmToken)}`,
      { token },
    );
  },

  /** C-CONFIRM commit: the ONLY write path — POST the token; the bound payload
   *  executes server-side. Single-use; an expired/forged token is refused.
   *  `enabledOps` (execute_plan only) names the destructive plan ops the human
   *  opted into; omitted/empty for every non-plan action. */
  confirmAction(domain: string, confirmToken: string, token: string, enabledOps?: string[]): Promise<unknown> {
    const body: Record<string, unknown> = { confirm_token: confirmToken };
    if (enabledOps && enabledOps.length > 0) body.enabled_ops = enabledOps;
    return apiJson<unknown>(`${actionsBase(domain)}/confirm`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  /** #27/#29/#30 coalesce commit: ONE call commits N child tokens for a domain that
   *  ships the batch endpoint (glossary today). Each child is verified/authorized/
   *  single-use-claimed and run through the SAME effect as /confirm; the result carries
   *  per-child applied/skipped/failed. Domains WITHOUT a batch endpoint loop confirmAction
   *  per token instead (the card decides — see BATCH_CONFIRM_DOMAINS). */
  confirmActionBatch(
    domain: string,
    childTokens: string[],
    token: string,
    enabledOps?: string[],
  ): Promise<BatchConfirmResult> {
    const body: Record<string, unknown> = { child_tokens: childTokens };
    if (enabledOps && enabledOps.length > 0) body.enabled_ops = enabledOps;
    return apiJson<BatchConfirmResult>(`${actionsBase(domain)}/confirm-batch`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  /** C-PROPOSE apply: a version-checked PATCH for a record edit. The domain owns
   *  the concrete row path; we pass the resource ref + base_version (If-Match) so
   *  drift surfaces as 409/412. The body mirrors the proposal's changes. */
  applyRecordEdit(
    domain: string,
    resourceRef: Record<string, unknown>,
    baseVersion: string,
    changes: RecordEditChange[],
    token: string,
  ): Promise<unknown> {
    return apiJson<unknown>(`${actionsBase(domain)}/apply-record-edit`, {
      method: 'PATCH',
      body: JSON.stringify({ resource_ref: resourceRef, changes }),
      token,
      headers: { 'If-Match': baseVersion },
    });
  },
};
