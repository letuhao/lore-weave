// ─────────────────────────────────────────────────────────────────────────────
// KG customizable-ontology API client (lane LE).
// Typed client for the /v1/kg/* surface (graph-schemas, adopt, sync, views,
// graph read, triage). Rides the shared `apiJson` (relative base → gateway,
// Bearer token, 204/401 handling). Source of truth: contracts/api/knowledge-
// service/{ontology,views,triage}.yaml. The real BE is built in parallel; at C3
// integration this client hits the live gateway unchanged (tests mock it).
// ─────────────────────────────────────────────────────────────────────────────

import { apiJson } from '../../../api';
import type {
  AdoptPayload,
  AdoptPreviewPayload,
  AdoptPreview,
  EdgeType,
  EdgeTypeCreate,
  FactType,
  FactTypeCreate,
  GraphReadParams,
  GraphSchemaSummary,
  GraphSchemaTree,
  GraphSchemaPatch,
  GraphSlice,
  GraphView,
  ResolvedSchema,
  Scope,
  SchemaNodeKind,
  SchemaNodeKindCreate,
  SyncApplyPayload,
  SyncApplyResult,
  SyncDiff,
  TriageGroupList,
  TriageListParams,
  TriageResolvePayload,
  TriageResolveResult,
  ViewCreate,
  VocabValue,
  VocabValueCreate,
} from '../types/ontology';

// All KG ontology routes are gateway-prefix-proxied under /v1/kg.
const BASE = '/v1/kg';

function qs(
  params: Record<string, string | number | boolean | undefined>,
): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

// The typed param interfaces (ListSchemasParams / GraphReadParams /
// TriageListParams) are structurally a Record of primitives, but TS won't widen
// an interface to an index signature implicitly — coerce at the boundary.
type QueryParams = Record<string, string | number | boolean | undefined>;

export interface ListSchemasParams {
  scope?: Scope | 'all';
  project_id?: string;
  include_deprecated?: boolean;
}

export const ontologyApi = {
  // ── graph schemas ──────────────────────────────────────────────────────────

  listSchemas(
    params: ListSchemasParams,
    token: string,
  ): Promise<{ items: GraphSchemaSummary[] }> {
    return apiJson(`${BASE}/graph-schemas${qs(params as QueryParams)}`, { token });
  },

  getSchema(schemaId: string, token: string): Promise<GraphSchemaTree> {
    return apiJson(`${BASE}/graph-schemas/${schemaId}`, { token });
  },

  patchSchema(
    schemaId: string,
    patch: GraphSchemaPatch,
    token: string,
  ): Promise<GraphSchemaSummary> {
    return apiJson(`${BASE}/graph-schemas/${schemaId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
      token,
    });
  },

  deprecateSchema(schemaId: string, token: string): Promise<void> {
    return apiJson(`${BASE}/graph-schemas/${schemaId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── resolved (effective) schema ──────────────────────────────────────────────

  getResolvedSchema(projectId: string, token: string): Promise<ResolvedSchema> {
    return apiJson(`${BASE}/projects/${projectId}/schema`, { token });
  },

  // ── adopt (copy-down) ────────────────────────────────────────────────────────

  // Returns the new project GraphSchemaSummary on 201. On the M1 422 the shared
  // apiJson throws an Error with `.status === 422` and `.body` = NeedsGlossary;
  // useOntologyAdopt reads that body to surface the deep-link state.
  adopt(
    projectId: string,
    payload: AdoptPayload,
    token: string,
  ): Promise<GraphSchemaSummary> {
    return apiJson(`${BASE}/projects/${projectId}/adopt`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  // ── adopt loss preview (read-only — "what you'll lose" on re-adopt) ───────────

  // Read-only POST (body carries the candidate source_schema_id). Returns
  // { has_current, would_lose:[...] }; useOntologyAdopt auto-fetches this on
  // template select so AdoptPicker can warn + gate before the destructive adopt.
  adoptPreview(
    projectId: string,
    payload: AdoptPreviewPayload,
    token: string,
  ): Promise<AdoptPreview> {
    return apiJson(`${BASE}/projects/${projectId}/adopt/preview`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  // ── sync (tree-granular diff/apply) ──────────────────────────────────────────

  syncAvailable(projectId: string, token: string): Promise<SyncDiff> {
    return apiJson(`${BASE}/projects/${projectId}/sync/available`, { token });
  },

  syncApply(
    projectId: string,
    payload: SyncApplyPayload,
    token: string,
  ): Promise<SyncApplyResult> {
    return apiJson(`${BASE}/projects/${projectId}/sync/apply`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  // ── schema children (additive + deprecate-only) ──────────────────────────────

  addEdgeType(
    schemaId: string,
    body: EdgeTypeCreate,
    token: string,
  ): Promise<EdgeType> {
    return apiJson(`${BASE}/graph-schemas/${schemaId}/edge-types`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  deprecateEdgeType(
    schemaId: string,
    code: string,
    token: string,
  ): Promise<void> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/edge-types/${encodeURIComponent(code)}`,
      { method: 'DELETE', token },
    );
  },

  addFactType(
    schemaId: string,
    body: FactTypeCreate,
    token: string,
  ): Promise<FactType> {
    return apiJson(`${BASE}/graph-schemas/${schemaId}/fact-types`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  addVocabValue(
    schemaId: string,
    setCode: string,
    body: VocabValueCreate,
    token: string,
  ): Promise<VocabValue> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/vocab-sets/${encodeURIComponent(setCode)}/values`,
      { method: 'POST', body: JSON.stringify(body), token },
    );
  },

  addNodeKind(
    schemaId: string,
    body: SchemaNodeKindCreate,
    token: string,
  ): Promise<SchemaNodeKind> {
    return apiJson(`${BASE}/graph-schemas/${schemaId}/node-kinds`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  // ── views (per-user lenses) ──────────────────────────────────────────────────

  listViews(projectId: string, token: string): Promise<{ items: GraphView[] }> {
    return apiJson(`${BASE}/projects/${projectId}/views`, { token });
  },

  createView(
    projectId: string,
    body: ViewCreate,
    token: string,
  ): Promise<GraphView> {
    return apiJson(`${BASE}/projects/${projectId}/views`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  upsertView(
    projectId: string,
    code: string,
    body: ViewCreate,
    token: string,
  ): Promise<GraphView> {
    return apiJson(
      `${BASE}/projects/${projectId}/views/${encodeURIComponent(code)}`,
      { method: 'PUT', body: JSON.stringify(body), token },
    );
  },

  deleteView(projectId: string, code: string, token: string): Promise<void> {
    return apiJson(
      `${BASE}/projects/${projectId}/views/${encodeURIComponent(code)}`,
      { method: 'DELETE', token },
    );
  },

  // ── graph read (view + temporal as-of) ───────────────────────────────────────

  readGraph(
    projectId: string,
    params: GraphReadParams,
    token: string,
  ): Promise<GraphSlice> {
    return apiJson(`${BASE}/projects/${projectId}/graph${qs(params as QueryParams)}`, {
      token,
    });
  },

  // ── triage queue ─────────────────────────────────────────────────────────────

  listTriage(
    projectId: string,
    params: TriageListParams,
    token: string,
  ): Promise<TriageGroupList> {
    return apiJson(`${BASE}/projects/${projectId}/triage${qs(params as QueryParams)}`, {
      token,
    });
  },

  resolveTriage(
    projectId: string,
    signature: string,
    body: TriageResolvePayload,
    token: string,
  ): Promise<TriageResolveResult> {
    return apiJson(
      `${BASE}/projects/${projectId}/triage/${encodeURIComponent(signature)}/resolve`,
      { method: 'POST', body: JSON.stringify(body), token },
    );
  },

  dismissTriageItem(
    projectId: string,
    triageId: string,
    token: string,
  ): Promise<void> {
    return apiJson(
      `${BASE}/projects/${projectId}/triage/${triageId}/dismiss`,
      { method: 'POST', token },
    );
  },
};

export type OntologyApi = typeof ontologyApi;
