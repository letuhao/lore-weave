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
  BlankSchemaCreate,
  CloneSchemaRequest,
  EdgeType,
  EdgeTypeCreate,
  EdgeTypePatch,
  FactType,
  FactTypeCreate,
  FactTypePatch,
  GraphReadParams,
  GraphSchemaSummary,
  GraphSchemaTree,
  GraphSchemaPatch,
  GraphSlice,
  GraphView,
  NodeKindPatch,
  ResolvedSchema,
  Scope,
  SchemaNodeKind,
  SchemaNodeKindCreate,
  SyncApplyPayload,
  SyncApplyResult,
  SyncDiff,
  TriageGroupList,
  TriageItemList,
  TriageListParams,
  TriageResolvePayload,
  TriageResolveResult,
  ViewCreate,
  VocabSet,
  VocabSetCreate,
  VocabSetPatch,
  VocabValue,
  VocabValueCreate,
  VocabValuePatch,
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

// The schema endpoints return vocab VALUES separately (`vocab_values`, keyed by
// set code) rather than nested in each `vocab_sets[]` row. Every FE consumer
// (SchemaEditor, the inspector) reads `vocab_sets[].values`, so nest them here at
// the read boundary — once, for both the tree and the resolved schema.
function nestVocabValues<T extends { vocab_sets?: VocabSet[]; vocab_values?: Record<string, VocabValue[]> }>(
  schema: T,
): T {
  const byCode = schema?.vocab_values;
  if (!byCode || !schema.vocab_sets) return schema;
  return {
    ...schema,
    vocab_sets: schema.vocab_sets.map((vs) => ({ ...vs, values: byCode[vs.code] ?? vs.values ?? [] })),
  };
}

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

  // `projectId` is REQUIRED to read a PROJECT-scoped schema: the BE visibility gate
  // (_visible) only exposes a project row to a caller passing its project_id (the
  // router grant-checks it). Omit it and a project schema 404s — pass it whenever
  // the schema might be project-scoped (the active project schema).
  getSchema(schemaId: string, token: string, projectId?: string): Promise<GraphSchemaTree> {
    return apiJson<GraphSchemaTree>(
      `${BASE}/graph-schemas/${schemaId}${qs({ project_id: projectId })}`,
      { token },
    ).then(nestVocabValues);
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

  // Clone (A2) — deep-copy any readable schema into a NEW user-scoped editable
  // template the caller owns (distinct from adopt's project-scoped replace).
  cloneSchema(body: CloneSchemaRequest, token: string): Promise<GraphSchemaSummary> {
    return apiJson(`${BASE}/graph-schemas`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  // ── resolved (effective) schema ──────────────────────────────────────────────

  getResolvedSchema(projectId: string, token: string): Promise<ResolvedSchema> {
    return apiJson<ResolvedSchema>(`${BASE}/projects/${projectId}/schema`, { token }).then(nestVocabValues);
  },

  // M1 — all node-kind + edge-type usage counts in one read (inline badges +
  // the delete-confirm gate; avoids N per-row calls).
  schemaUsageSummary(
    projectId: string,
    token: string,
  ): Promise<{ node_kind: Record<string, number>; edge_type: Record<string, number> }> {
    return apiJson(`${BASE}/projects/${projectId}/schema/usage-summary`, { token });
  },

  // M3b — generate a schema proposal from a premise (single-shot LLM; nothing
  // written — the caller adopts the ticked components via the add routes).
  schemaPropose(
    projectId: string,
    body: import('../types/ontology').SchemaProposeRequest,
    token: string,
  ): Promise<import('../types/ontology').SchemaProposal> {
    return apiJson(`${BASE}/projects/${projectId}/schema/propose`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  // M3a — the node kinds + edge types the project's extracted graph already has.
  schemaObserved(
    projectId: string,
    token: string,
  ): Promise<import('../types/ontology').ObservedComponents> {
    return apiJson(`${BASE}/projects/${projectId}/schema/observed`, { token });
  },

  // A4 — how many graph elements reference a schema component (delete warning).
  // `counted=false` for fact_type/vocab_value (fuzzier usage → plain confirm).
  schemaComponentUsage(
    projectId: string,
    nodeType: string,
    code: string,
    token: string,
  ): Promise<{ node_type: string; code: string; count: number; counted: boolean }> {
    return apiJson(
      `${BASE}/projects/${projectId}/schema/usage${qs({ node_type: nodeType, code })}`,
      { token },
    );
  },

  // Create-from-scratch (A2) — a blank project schema (no template first).
  createBlankSchema(
    projectId: string,
    body: BlankSchemaCreate,
    token: string,
  ): Promise<GraphSchemaSummary> {
    return apiJson(`${BASE}/projects/${projectId}/schema`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
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

  // ── schema children — full CRUD (A1). PATCH is attribute-only; `code` is
  //    IMMUTABLE. DELETE is tier-aware server-side (user-tier HARD, project SOFT).
  //    An `add` of a soft-deprecated code REVIVES it (server-side revive-on-recreate).

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

  patchEdgeType(
    schemaId: string,
    code: string,
    patch: EdgeTypePatch,
    token: string,
  ): Promise<EdgeType> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/edge-types/${encodeURIComponent(code)}`,
      { method: 'PATCH', body: JSON.stringify(patch), token },
    );
  },

  deleteEdgeType(
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

  patchFactType(
    schemaId: string,
    code: string,
    patch: FactTypePatch,
    token: string,
  ): Promise<FactType> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/fact-types/${encodeURIComponent(code)}`,
      { method: 'PATCH', body: JSON.stringify(patch), token },
    );
  },

  deleteFactType(
    schemaId: string,
    code: string,
    token: string,
  ): Promise<void> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/fact-types/${encodeURIComponent(code)}`,
      { method: 'DELETE', token },
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

  patchNodeKind(
    schemaId: string,
    code: string,
    patch: NodeKindPatch,
    token: string,
  ): Promise<SchemaNodeKind> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/node-kinds/${encodeURIComponent(code)}`,
      { method: 'PATCH', body: JSON.stringify(patch), token },
    );
  },

  deleteNodeKind(
    schemaId: string,
    code: string,
    token: string,
  ): Promise<void> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/node-kinds/${encodeURIComponent(code)}`,
      { method: 'DELETE', token },
    );
  },

  // ── vocab sets (create/patch/delete) + values (add/patch/delete) ───────────

  addVocabSet(
    schemaId: string,
    body: VocabSetCreate,
    token: string,
  ): Promise<VocabSet> {
    return apiJson(`${BASE}/graph-schemas/${schemaId}/vocab-sets`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  patchVocabSet(
    schemaId: string,
    setCode: string,
    patch: VocabSetPatch,
    token: string,
  ): Promise<VocabSet> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/vocab-sets/${encodeURIComponent(setCode)}`,
      { method: 'PATCH', body: JSON.stringify(patch), token },
    );
  },

  deleteVocabSet(
    schemaId: string,
    setCode: string,
    token: string,
  ): Promise<void> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/vocab-sets/${encodeURIComponent(setCode)}`,
      { method: 'DELETE', token },
    );
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

  patchVocabValue(
    schemaId: string,
    setCode: string,
    code: string,
    patch: VocabValuePatch,
    token: string,
  ): Promise<VocabValue> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/vocab-sets/${encodeURIComponent(setCode)}/values/${encodeURIComponent(code)}`,
      { method: 'PATCH', body: JSON.stringify(patch), token },
    );
  },

  deleteVocabValue(
    schemaId: string,
    setCode: string,
    code: string,
    token: string,
  ): Promise<void> {
    return apiJson(
      `${BASE}/graph-schemas/${schemaId}/vocab-sets/${encodeURIComponent(setCode)}/values/${encodeURIComponent(code)}`,
      { method: 'DELETE', token },
    );
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

  // S-05 — the pending items of one signature (per-item drill-in), so the FE can
  // dismiss a single noisy item via dismissTriageItem instead of the whole group.
  listTriageItems(
    projectId: string,
    signature: string,
    token: string,
  ): Promise<TriageItemList> {
    return apiJson(
      `${BASE}/projects/${projectId}/triage/${encodeURIComponent(signature)}/items`,
      { token },
    );
  },
};

export type OntologyApi = typeof ontologyApi;
