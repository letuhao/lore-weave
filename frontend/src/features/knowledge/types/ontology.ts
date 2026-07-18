// ─────────────────────────────────────────────────────────────────────────────
// KG customizable-ontology types (lane LE).
// Mirrors contracts/api/knowledge-service/{ontology,views,triage}.yaml — the
// FROZEN S0/C0 shape. Keep field names verbatim with the contract so the
// mock→real API swap at C3 is a no-op for these types.
// ─────────────────────────────────────────────────────────────────────────────

export type Scope = 'system' | 'user' | 'project';
export type Strength = 'required' | 'optional';
export type Cardinality = 'single_active' | 'multi_active';

// ── graph schemas ────────────────────────────────────────────────────────────

export interface GraphSchemaSummary {
  schema_id: string;
  scope: Scope;
  scope_id?: string | null;
  code: string;
  name: string;
  description?: string | null;
  schema_version: number;
  /**
   * Q2 (LOCKED): true => off-vocab predicates allowed (today's behaviour);
   * false => closed to declared edge types (off-vocab → triage).
   */
  allow_free_edges: boolean;
  content_hash?: string | null;
  source_ref?: string | null;
  source_hash?: string | null;
  deprecated_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface EdgeType {
  edge_type_id?: string;
  code: string;
  label: string;
  directed: boolean;
  source_node_kinds?: string[];
  target_node_kinds?: string[];
  /** true => every instance requires valid_from + EVIDENCED_BY */
  temporal: boolean;
  provenance_required?: boolean;
  cardinality: Cardinality;
  description?: string | null;
  deprecated_at?: string | null;
}

export interface EdgeTypeCreate {
  code: string;
  label: string;
  directed?: boolean;
  source_node_kinds?: string[];
  target_node_kinds?: string[];
  temporal?: boolean;
  provenance_required?: boolean;
  cardinality?: Cardinality;
  description?: string;
}

export interface FactType {
  fact_type_id?: string;
  code: string;
  label: string;
  description?: string | null;
  deprecated_at?: string | null;
}

export interface FactTypeCreate {
  code: string;
  label: string;
  description?: string;
}

export interface VocabValue {
  vocab_value_id?: string;
  code: string;
  label: string;
  metadata?: Record<string, unknown>;
}

export interface VocabValueCreate {
  code: string;
  label: string;
  metadata?: Record<string, unknown>;
}

export interface VocabSet {
  vocab_set_id?: string;
  code: string;
  label: string;
  description?: string | null;
  /** true => extractor may only assign, not coin new values */
  closed: boolean;
  values?: VocabValue[];
}

export interface SchemaNodeKind {
  schema_node_kind_id?: string;
  kind_code: string;
  strength: Strength;
  deprecated_at?: string | null;
}

export interface SchemaNodeKindCreate {
  kind_code: string;
  strength: Strength;
}

export interface GraphSchemaTree extends GraphSchemaSummary {
  edge_types?: EdgeType[];
  fact_types?: FactType[];
  vocab_sets?: VocabSet[];
  /** BE returns vocab values SEPARATELY, keyed by vocab-set code (not nested in
   *  each set). `ontologyApi` nests them into `vocab_sets[].values` on read. */
  vocab_values?: Record<string, VocabValue[]>;
  node_kinds?: SchemaNodeKind[];
}

export interface GraphSchemaPatch {
  name?: string;
  description?: string;
  allow_free_edges?: boolean;
}

// ── full-CRUD authoring (A1/A2) — PATCH bodies are attribute-only; `code` is
//    IMMUTABLE (a rename = deprecate + create-new). ──────────────────────────
export interface EdgeTypePatch {
  label?: string;
  directed?: boolean;
  source_node_kinds?: string[];
  target_node_kinds?: string[];
  temporal?: boolean;
  provenance_required?: boolean;
  cardinality?: Cardinality;
  description?: string;
}

export interface FactTypePatch {
  label?: string;
  description?: string;
}

export interface NodeKindPatch {
  strength: Strength;
}

export interface VocabSetCreate {
  code: string;
  label: string;
  description?: string;
  closed?: boolean;
}

export interface VocabSetPatch {
  label?: string;
  description?: string;
  closed?: boolean;
}

export interface VocabValuePatch {
  label?: string;
  metadata?: Record<string, unknown>;
}

/** Create-from-scratch (A2) — a blank project schema (no template). */
export interface BlankSchemaCreate {
  name: string;
  description?: string;
  allow_free_edges?: boolean;
}

/** Clone a readable schema into a NEW user-scoped editable template (A2). */
export interface CloneSchemaRequest {
  source_schema_id: string;
  name?: string;
}

/** M3a — what the project's extracted graph already contains (to promote into the schema). */
export interface ObservedComponents {
  node_kinds: { code: string; count: number }[];
  edge_types: { code: string; count: number; source_kinds: string[]; target_kinds: string[] }[];
}

/** M3b — a schema proposal generated from a premise (LLM, propose→confirm). */
export interface SchemaProposeRequest {
  premise: string;
  genre?: string;
  model_ref: string;
}
export interface SchemaProposal {
  node_kinds: { code: string; label?: string }[];
  edge_types: { code: string; label?: string; source_kinds: string[]; target_kinds: string[] }[];
  fact_types: { code: string; label?: string }[];
}

export interface ResolvedSchema {
  project_id: string;
  schema_version: number;
  allow_free_edges: boolean;
  edge_types?: EdgeType[];
  fact_types?: FactType[];
  vocab_sets?: VocabSet[];
  /** Separate, keyed by vocab-set code (see GraphSchemaTree). Nested into
   *  `vocab_sets[].values` by `ontologyApi` on read. */
  vocab_values?: Record<string, VocabValue[]>;
  node_kinds?: SchemaNodeKind[];
}

// ── adopt ─────────────────────────────────────────────────────────────────────

export interface AdoptPayload {
  source_schema_id: string;
  /** proceed past missing `optional` kinds without re-warning */
  acknowledge_optional_gaps?: boolean;
}

/** Body of the M1 422 — adopt blocked on missing `required` glossary kinds. */
export interface NeedsGlossary {
  code: string;
  message: string;
  needs_glossary: {
    /** present when the project has a book; else kinds resolve vs user glossary standards */
    book_id?: string | null;
    /** the missing `required` node-kind codes the user must add in glossary first */
    kinds: string[];
  };
}

// ── adopt loss preview (re-adopt "what you'll lose") ──────────────────────────

export interface AdoptPreviewPayload {
  /** the candidate template to re-adopt; preview reports what the swap drops */
  source_schema_id: string;
}

/** One customization re-adopt would drop (removed_upstream) or overwrite (modified). */
export interface AdoptLoss {
  node_type: SyncNodeType;
  parent_code?: string | null;
  code: string;
  /** 'removed_upstream' = vanishes; 'modified' = overwritten by the template */
  change: 'removed_upstream' | 'modified';
  fields_changed?: string[];
}

export interface AdoptPreview {
  /** false => project never adopted; nothing to lose */
  has_current: boolean;
  would_lose: AdoptLoss[];
}

// ── sync ──────────────────────────────────────────────────────────────────────

export type SyncNodeType =
  | 'edge_type'
  | 'fact_type'
  | 'vocab_set'
  | 'vocab_value'
  | 'node_kind';

export type SyncChangeKind = 'added' | 'modified' | 'removed_upstream';

export interface SyncChange {
  node_type: SyncNodeType;
  parent_code?: string | null;
  code: string;
  change: SyncChangeKind;
  fields_changed?: string[];
  upstream?: Record<string, unknown> | null;
  mine?: Record<string, unknown> | null;
}

export interface SyncDiff {
  source_ref?: string | null;
  source_hash_current?: string | null;
  project_source_hash?: string | null;
  has_updates: boolean;
  changes: SyncChange[];
}

export type SyncChoice = 'keep_mine' | 'take_theirs';

export interface SyncDecision {
  node_type: SyncNodeType;
  parent_code?: string | null;
  code: string;
  choice: SyncChoice;
}

export interface SyncApplyPayload {
  /** the source_hash_current returned by /sync/available (optimistic-concurrency token) */
  base_source_hash: string;
  decisions: SyncDecision[];
}

export interface SyncApplyResult {
  schema_version: number;
  source_hash: string;
  applied: number;
}

// ── views ─────────────────────────────────────────────────────────────────────

export interface GraphView {
  view_id: string;
  project_id: string;
  user_id?: string;
  code: string;
  name: string;
  description?: string | null;
  edge_type_codes: string[];
  node_kind_codes: string[];
  created_at?: string;
  updated_at?: string;
}

export interface ViewCreate {
  /** slugified from name when omitted */
  code?: string;
  name: string;
  description?: string;
  edge_type_codes?: string[];
  node_kind_codes?: string[];
}

// ── graph read (temporal) ─────────────────────────────────────────────────────

export interface GraphNode {
  id: string;
  kind: string;
  name: string;
  glossary_entity_id?: string | null;
  // KG-ML M5 (C7) — localized labels for a reader whose language differs from
  // the source. null ⇒ keep the canonical kind/name (explicit source fallback).
  kind_label?: string | null;
  name_label?: string | null;
}

export interface GraphEdge {
  edge_type: string;
  source_id: string;
  target_id: string;
  valid_from?: number | null;
  valid_to?: number | null;
  schema_version?: number | null;
  // KG-ML M5 (C7) — localized predicate label (curated → humanized fallback).
  edge_type_label?: string | null;
}

export interface GraphSlice {
  as_of_chapter?: number | null;
  view?: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  warnings?: string[];
}

export interface GraphReadParams {
  /** view code; omitted = whole resolved schema */
  view?: string;
  /** chapter ordinal; omitted = latest (all open instances) */
  as_of_chapter?: number;
  limit?: number;
}

// ── triage ────────────────────────────────────────────────────────────────────

export type TriageItemType =
  | 'unknown_node_kind'
  | 'unknown_edge_type'
  | 'edge_kind_mismatch'
  | 'unknown_vocab_value'
  | 'edge_cardinality_conflict';

export type TriageStatus =
  | 'pending'
  | 'pending_glossary'
  | 'resolved'
  | 'dismissed';

export interface TriageGroup {
  signature: string;
  item_type: TriageItemType;
  count: number;
  status: TriageStatus;
  sample_payload?: Record<string, unknown>;
  suggested_actions?: string[];
}

export interface TriageGroupList {
  groups: TriageGroup[];
  next_cursor?: string | null;
}

// S-05 — per-item drill-in of a signature group (for single-item dismiss).
export interface TriageItem {
  triage_id: string;
  item_type: TriageItemType;
  payload?: Record<string, unknown>;
}

export interface TriageItemList {
  items: TriageItem[];
}

export interface TriageListParams {
  status?: TriageStatus;
  item_type?: TriageItemType;
  limit?: number;
  cursor?: string;
}

export type TriageAction =
  | 'map'
  | 'add_to_vocab'
  | 'add_to_schema'
  | 're_target'
  | 'widen_target_kinds'
  | 'drop_edge'
  | 'close_previous'
  | 'set_multi_active'
  | 'promote_to_glossary_kind'
  | 'demote_to_attribute'
  | 'dismiss';

export interface TriageResolvePayload {
  action: TriageAction;
  params?: Record<string, unknown>;
  /** when true, batch-apply to every pending item of this signature */
  apply_to_signature?: boolean;
}

export interface TriageResolveResult {
  status: 'resolved' | 'pending_glossary';
  affected: number;
  schema_version?: number | null;
  needs_glossary?: {
    book_id?: string | null;
    kinds: string[];
  } | null;
}
