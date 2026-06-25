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

/** One field change in a `propose_record_edit` diff. */
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
