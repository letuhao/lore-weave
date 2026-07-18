// W10 arc-timeline — the arc-template API layer. Relative `/v1/composition/arc-templates*`
// rides the Vite proxy → gateway (dev :3123) / nginx (prod). Mirrors motifApi exactly
// (tenancy, the uniform H13 404, If-Match optimistic concurrency). The `apply` call is
// the §12.5 PURE preview — it returns a deterministic plan, persists nothing.
import { apiJson } from '../../../api';
import type {
  ArcApplyArgs, ArcApplyPlan, ArcMaterializeArgs, ArcMaterializeResult, ArcTemplate,
  ArcTemplateCreateArgs, ArcTemplateList, ArcTemplateListParams, ArcTemplatePatchArgs,
} from './arcTypes';

const BASE = '/v1/composition';

function _qs(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') usp.set(k, String(v));
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export const arcApi = {
  list(params: ArcTemplateListParams, token: string): Promise<ArcTemplateList> {
    return apiJson<ArcTemplateList>(`${BASE}/arc-templates${_qs(params)}`, { token });
  },
  get(arcId: string, token: string): Promise<ArcTemplate> {
    return apiJson<ArcTemplate>(`${BASE}/arc-templates/${arcId}`, { token });
  },
  create(args: ArcTemplateCreateArgs, token: string): Promise<ArcTemplate> {
    return apiJson<ArcTemplate>(`${BASE}/arc-templates`, {
      method: 'POST', body: JSON.stringify(args), token,
    });
  },
  /** Owner-only edit. If-Match → 412 on a version conflict (the hook surfaces the
   *  server's current row so the editor can reconcile). */
  patch(arcId: string, args: ArcTemplatePatchArgs, expectedVersion: number, token: string): Promise<ArcTemplate> {
    return apiJson<ArcTemplate>(`${BASE}/arc-templates/${arcId}`, {
      method: 'PATCH',
      body: JSON.stringify(args),
      headers: { 'If-Match': String(expectedVersion) },
      token,
    });
  },
  archive(arcId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/arc-templates/${arcId}`, { method: 'DELETE', token });
  },
  /** S-08 — un-archive (reverse of archive). Owner-only; pass book_id to restore a shared row. */
  restore(arcId: string, token: string, bookId?: string): Promise<ArcTemplate> {
    const qs = bookId ? `?book_id=${encodeURIComponent(bookId)}` : '';
    return apiJson<ArcTemplate>(`${BASE}/arc-templates/${arcId}/restore${qs}`, { method: 'POST', token });
  },
  /** Adopt = clone-to-customize into the caller's own tier (cross-genre retag). */
  adopt(arcId: string, retagGenres: string[] | undefined, token: string): Promise<ArcTemplate> {
    return apiJson<ArcTemplate>(`${BASE}/arc-templates/${arcId}/adopt`, {
      method: 'POST',
      body: JSON.stringify(retagGenres ? { retag_genres: retagGenres } : {}),
      token,
    });
  },
  /** Apply-PREVIEW (§12.5): deterministic rescale + roster-bind + drop/merge plan.
   *  PURE — nothing is persisted; the caller renders the plan for review. */
  apply(arcId: string, args: ArcApplyArgs, token: string): Promise<ArcApplyPlan> {
    return apiJson<ArcApplyPlan>(`${BASE}/arc-templates/${arcId}/apply`, {
      method: 'POST', body: JSON.stringify(args), token,
    });
  },
  /** MATERIALIZE (D-W10-APPLY-PLANNER-MATERIALIZE): commit the arc onto THIS work's
   *  book — a real arc→chapter→scene outline + motif_application ledger. Work-scoped
   *  (not arc-scoped). 409 if a chapter is already planned (resend with replace). */
  materialize(projectId: string, args: ArcMaterializeArgs, token: string): Promise<ArcMaterializeResult> {
    return apiJson<ArcMaterializeResult>(`${BASE}/works/${projectId}/arc/materialize`, {
      method: 'POST', body: JSON.stringify(args), token,
    });
  },
  /** S-10 O6a — "Save this arc as a template": extract an AUTHORED arc (a structure_node) into the
   *  caller's own arc-template library. Reading the arc ⇒ VIEW on its book; the new template is
   *  owner-stamped to the caller. 409 (ARC_TEMPLATE_CODE_EXISTS) on a duplicate (owner, code, lang). */
  extractTemplate(nodeId: string, args: ArcExtractArgs, token: string): Promise<ArcTemplate> {
    return apiJson<ArcTemplate>(`${BASE}/arcs/${nodeId}/extract-template`, {
      method: 'POST', body: JSON.stringify(args), token,
    });
  },
  /** S-10 O6b — "Suggest an arc for this premise": rank the caller-visible arc templates that fit a
   *  Work's premise/genre. Read-only (VIEW on the Work's book). */
  suggest(args: ArcSuggestArgs, token: string): Promise<ArcSuggestResult> {
    return apiJson<ArcSuggestResult>(`${BASE}/arc-templates/suggest`, {
      method: 'POST', body: JSON.stringify(args), token,
    });
  },
};

// S-10 O6 — request/response shapes for the two direct arc-agent routes (co-located; they don't
// touch the shared arcTypes surface). Kinds are the route's own closed sets.
export type ArcExtractArgs = {
  code: string;
  name: string;
  language?: string;
  visibility?: 'private' | 'unlisted';
};

export type ArcSuggestArgs = {
  project_id: string;
  premise?: string;
  genre?: string;
  limit?: number;
  detail?: 'summary' | 'full';
};

export type ArcSuggestCandidate = {
  arc_template: ArcTemplate;
  score: number;
  match_reason: string | null;
};

export type ArcSuggestResult = {
  candidates: ArcSuggestCandidate[];
  detail: string;
  count: number;
};
