import { apiJson } from '../../api';
import type {
  BenchmarkRunResponse,
  BenchmarkStatus,
  ExtractionConfigPayload,
  Project,
  ProjectCreatePayload,
  ProjectListParams,
  ProjectListResponse,
  ProjectUpdatePayload,
  SummariesListResponse,
  Summary,
  SummaryUpdatePayload,
  SummaryVersion,
  SummaryVersionListResponse,
  UserDataDeleteResponse,
} from './types';
import type {
  CostEstimate,
  ExtractionJobStatus,
} from './types/projectState';

// ── K19a.4 — Extraction wire types ───────────────────────────────────────
// Mirrors services/knowledge-service/app/db/repositories/extraction_jobs.py.
// Note: BE ships `scope` as a bare string literal, not the UI's
// discriminated-union JobScope. The hook converts between the two.
export type ExtractionJobScopeWire =
  | 'all'
  | 'chapters'
  | 'chat'
  | 'glossary_sync';

// T4.1 — the canon-growth delta surfaced by the composition Flywheel panel.
export interface FlywheelItemWire {
  kind: 'entity' | 'event' | 'relation';
  id: string;
  name: string;
}
export interface FlywheelDeltaWire {
  has_delta: boolean;
  job_id: string | null;
  completed_at: string | null;
  entities_added: number;
  relations_added: number;
  events_added: number;
  new_items: FlywheelItemWire[];
}

export interface ExtractionJobWire {
  job_id: string;
  user_id: string;
  project_id: string;
  scope: ExtractionJobScopeWire;
  scope_range: Record<string, unknown> | null;
  status: ExtractionJobStatus;
  llm_model: string;
  embedding_model: string;
  max_spend_usd: string | null;
  items_processed: number;
  items_total: number | null;
  cost_spent_usd: string;
  current_cursor: Record<string, unknown> | null;
  /**
   * C7 raise-cap (KN-7) — the job's parallel-LLM concurrency cap. `null`
   * ⇒ unbounded (started without a cap). The running-build control reads
   * this and PATCHes it in-flight. Optional in practice during a
   * rollout window where an older BE response lacks the field, so
   * consumers should treat `undefined`/`null` identically.
   */
  concurrency_level: number | null;
  started_at: string;
  paused_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  error_message: string | null;
  /**
   * K19b.2: populated only by `knowledgeApi.listAllJobs`. Per-project
   * routes (`listExtractionJobs`) and the single-job detail route
   * leave this `null`; those callers already have the project in
   * scope, so the BE skips the LEFT JOIN. Consumers that need the
   * name from a per-project context should read it from the Project
   * object directly, not this field.
   */
  project_name: string | null;
  /**
   * C6 (D-K19b.3-01) — human-readable chapter title for the job's
   * current cursor position. Present when `current_cursor.last_chapter_id`
   * is set AND book-service resolved it successfully. `null` for:
   *   - jobs without a cursor (newly-queued, completed, failed)
   *   - cursors without `last_chapter_id` (chat-scope uses `last_pending_id`)
   *   - any book-service failure (graceful degrade)
   * JobDetailPanel renders the "Current chapter" section only when
   * this field is populated.
   *
   * /review-impl L6: during BE→FE rollout, pre-C6 knowledge-service
   * responses lack this field entirely. At runtime the property is
   * `undefined`, not `null` — nullish coalescing (`??`) handles both
   * identically, so consumers SHOULD use `job.current_chapter_title
   * ?? fallback` rather than direct access. The type is kept as
   * `string | null` (not `?: string | null`) to force tsc to flag
   * fixtures that forget the field; runtime consumers still tolerate
   * undefined via the `??` pattern.
   */
  current_chapter_title: string | null;
}

/**
 * C11 (D-K19b.1-01) — envelope for ``GET /extraction/jobs``. Paired
 * with ``next_cursor`` so the FE can advance to more history pages.
 * ``next_cursor`` is ``null`` on the last page.
 */
export interface ExtractionJobsPageResponse {
  items: ExtractionJobWire[];
  next_cursor: string | null;
}

export interface GraphStatsResponse {
  project_id: string;
  entity_count: number;
  fact_count: number;
  event_count: number;
  passage_count: number;
  /** ISO-8601 UTC, or null if never extracted. */
  last_extracted_at: string | null;
}

export type { CostEstimate } from './types/projectState';

// K19a.5 — /extraction/estimate payload. Mirrors EstimateRequest in
// services/knowledge-service/app/routers/public/extraction.py. BE does
// NOT take embedding_model or max_spend_usd on estimate — keep the
// contract narrow so a future `extra="forbid"` on BE wouldn't reject us.
export interface EstimateExtractionPayload {
  scope: ExtractionJobScopeWire;
  scope_range?: { chapter_range: [number, number] };
  llm_model: string;
  // C13 — number of glossary entities the user intends to pin. Drives the
  // pinned-injection cost line (pinned_count × ~50 × num_windows). Omit ⇒ 0.
  pinned_count?: number;
}

// Mirrors StartJobRequest in
// services/knowledge-service/app/routers/public/extraction.py — BOTH
// llm_model and embedding_model are required by the BE; omitting either
// returns 422. Callers must have a prior job or a user-selected model.
// C12 — target-typed extraction taxonomy (mirrors StartJobRequest's
// ExtractionTarget Literal). `summaries` is the summary-enqueue pass;
// the FE picker's "events·timeline" label is the `events` op.
export type ExtractionTarget =
  | 'entities'
  | 'relations'
  | 'events'
  | 'facts'
  | 'summaries';

export interface ExtractionStartPayload {
  scope: ExtractionJobScopeWire;
  scope_range?: { chapter_range: [number, number] };
  llm_model: string;
  embedding_model: string;
  max_spend_usd?: string;
  items_total?: number;
  // C12 — the subset of passes to run. Omitted ⇒ all (back-compat). The BE
  // validator auto-includes `entities` for dependent targets.
  targets?: ExtractionTarget[];
  // C12 — passthrough cap on parallel LLM calls. Omitted ⇒ unbounded.
  concurrency_level?: number;
  // Reasoning enable/disable for the extraction LLM. 'none' (default) disables
  // hidden thinking — best for the JSON extraction pipeline (thinking can burn the
  // output budget / corrupt the array). 'medium' enables it for hard content. The
  // BE clamps to the caller's grant. Omitted ⇒ BE default ('none').
  reasoning_effort?: 'none' | 'low' | 'medium' | 'high';
  // C13 — glossary entity ids to pin (force-inject into every extraction
  // window's known_entities). Omitted / empty ⇒ no pins (back-compat).
  pinned_glossary_entity_ids?: string[];
}

// C13 — one entity in the build-wizard auto-pin suggestion data. Mirrors
// GlossaryEntityStat in services/knowledge-service/.../entities.py (which
// proxies glossary-service's /internal/books/{id}/entities/stats).
export interface GlossaryEntityStat {
  entity_id: string;
  name: string;
  kind: string;
  mention_count: number;
  first_chapter_index: number | null;
  last_chapter_index: number | null;
  // distinct linked chapters / total book chapters, in [0,1].
  coverage_pct: number;
}

export interface GlossaryEntityStatsResponse {
  items: GlossaryEntityStat[];
  chapter_count: number;
}

// Mirrors RebuildRequest (no `scope` field — handler hard-codes scope=all).
export interface RebuildPayload {
  llm_model: string;
  embedding_model: string;
  max_spend_usd?: string;
}

// bug #14 — without `?confirm=true` the rebuild BE returns this destructive
// preview (carrying live node counts) and deletes NOTHING; with it, the
// rebuild runs and returns the new ExtractionJob.
export interface RebuildWarning {
  warning: string;
  entity_count: number;
  fact_count: number;
  event_count: number;
  action_required: 'confirm';
}

// K19a.6 — discriminated return type for PUT /embedding-model.
// Without `?confirm=true` the BE returns a warning preview; with it
// the destructive change runs and the BE returns the result metadata.
// The same-model path returns a third `{message, current_model}` shape
// which we fold into the warning variant's unknown fields.
export interface ChangeEmbeddingModelWarning {
  warning: string;
  current_model: string;
  new_model: string;
  action_required: 'confirm';
}
export interface ChangeEmbeddingModelNoop {
  message: string;
  current_model: string;
}
export interface ChangeEmbeddingModelResult {
  project_id: string;
  previous_model: string;
  new_model: string;
  nodes_deleted: number;
  extraction_status: 'disabled';
}
export type ChangeEmbeddingModelResponse =
  | ChangeEmbeddingModelWarning
  | ChangeEmbeddingModelNoop
  | ChangeEmbeddingModelResult;

// K19c.4 — user-scope entity (from the Track 2 Neo4j graph, projected
// into the shape returned by /v1/knowledge/me/entities). Mirrors
// services/knowledge-service/app/db/neo4j_repos/entities.py::Entity.
export interface Entity {
  id: string;
  user_id: string;
  project_id: string | null;
  name: string;
  canonical_name: string;
  kind: string;
  aliases: string[];
  canonical_version: number;
  source_types: string[];
  confidence: number;
  glossary_entity_id: string | null;
  anchor_score: number;
  archived_at: string | null;
  archive_reason: string | null;
  /** C8: DERIVED server-side from glossary_entity_id + archived_at.
   *  `canonical` = glossary-anchored · `discovered` = unanchored active ·
   *  `archived` = archived_at set. Precedence archived > canonical >
   *  discovered (mirrors the BE `Entity.status` computed field). Never
   *  a stored column. Optional in the type so pre-C8 fixtures / a
   *  rollout-window response without the field degrade gracefully. */
  status?: EntityStatus;
  evidence_count: number;
  mention_count: number;
  /** K19d γ-a: set to true by PATCH /entities/{id}; gates the Unlock
   *  CTA in the detail panel. Extractions no longer re-append removed
   *  aliases until the user explicitly unlocks. */
  user_edited: boolean;
  /** C9 (D-K19d-γa-01): optimistic-concurrency counter. The FE sends
   *  this back via ``If-Match: W/"<version>"`` on PATCH. Bumped by
   *  every user-facing write on the BE. */
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserEntitiesResponse {
  entities: Entity[];
}

// K19b.8 — job logs. Cursor = log_id; page is full when
// len(logs) === limit, in which case next_cursor = max(log_id) and
// callers refetch with since_log_id = next_cursor. `null` cursor
// signals end-of-stream.
export type JobLogLevel = 'info' | 'warning' | 'error';

export interface JobLog {
  log_id: number;
  job_id: string;
  user_id: string;
  level: JobLogLevel;
  message: string;
  context: Record<string, unknown>;
  created_at: string;
}

export interface JobLogsResponse {
  logs: JobLog[];
  next_cursor: number | null;
}

// Studio Quality tab (`quality-canon`) / D-KG-CANON-FLAG-REVIEW-UI — a JobLog row
// whose context carries a confirmed pass2_canon_flag; same shape as JobLog, listed
// separately from the raw job-logs stream (project-wide, event-filtered).
export type CanonFlag = JobLog;

export interface CanonFlagsResponse {
  flags: CanonFlag[];
}

// K19b.6 — GET /v1/knowledge/costs response shape. Decimal fields land
// as JSON strings; callers cast via Number() for display arithmetic.
// `monthly_budget_usd` and `monthly_remaining_usd` are null when the
// user hasn't set a user-wide cap via PUT /me/budget.
export interface UserCostSummary {
  all_time_usd: string;
  current_month_usd: string;
  monthly_budget_usd: string | null;
  monthly_remaining_usd: string | null;
}

// K19b.6 — PUT /v1/knowledge/me/budget body + response.
export interface SetUserBudgetPayload {
  ai_monthly_budget_usd: string | null;
}
export interface SetUserBudgetResponse {
  user_id: string;
  ai_monthly_budget_usd: string | null;
}

// K19a.6 — POST /extraction/disable response. Non-destructive flip
// of extraction_enabled=false while preserving Neo4j graph data.
export interface DisableExtractionResponse {
  project_id: string;
  extraction_status: string;
  graph_preserved: boolean;
  /** Set on the idempotent no-op path ("already disabled"). */
  message?: string;
}

// K19a.6 review-impl F3 — DELETE /extraction/graph returns a 200 body
// with the delete summary, not 204. Prior FE type was `Promise<void>`
// which drops the body silently. No caller currently reads these
// fields, but typing them keeps the FE↔BE contract honest and makes
// "how many nodes did we delete?" one TS inference away.
export interface DeleteGraphResponse {
  project_id: string;
  nodes_deleted: number;
  extraction_status: 'disabled';
}

// ── K20α — summary regeneration ────────────────────────────────────────

export interface RegenerateRequest {
  model_source: 'user_model' | 'platform_model';
  model_ref: string;
}

/**
 * K20α wire type for POST /v1/knowledge/me/summary/regenerate. Only
 * the 200-status subset shows up here; 409 (`user_edit_lock` /
 * `regen_concurrent_edit`) and 422 (`regen_guardrail_failed`) come
 * through as structured `detail.error_code` bodies that the hook
 * inspects — see `useRegenerateBio`.
 */
export type RegenerateStatus =
  | 'regenerated'
  | 'no_op_similarity'
  | 'no_op_empty_source';

export interface RegenerateResponse {
  status: RegenerateStatus;
  summary: Summary | null;
  skipped_reason: string | null;
}

// ── K19d.2 / K19d.4 — entities browse + detail ────────────────────────

/** C8: closed set of derived entity statuses. Source of truth for the
 *  FE — the status filter + the row glyph map iterate this tuple. */
export const ENTITY_STATUSES = ['canonical', 'discovered', 'archived'] as const;
export type EntityStatus = (typeof ENTITY_STATUSES)[number];

/** C8: ordering keys accepted by the entities list endpoint. */
export type EntitySortBy = 'mention_count' | 'anchor_score';

export interface EntitiesListParams {
  project_id?: string;
  kind?: string;
  /** FE enforces min length 2 (matches BE Query min_length=2) so
   *  filter-free short keystrokes don't round-trip to a 422. */
  search?: string;
  /** C8: natural-language VECTOR search. Mutually exclusive with
   *  `search` (BE 422s if both set); requires `project_id`. */
  semantic_query?: string;
  /** C8: filter to a single derived status. */
  status?: EntityStatus;
  /** C8: ordering key. Defaults to `mention_count` BE-side. */
  sort_by?: EntitySortBy;
  limit?: number;
  offset?: number;
  /** W11 reader spoiler window: restrict to entities met by this chapter
   *  (a fact established by it). Fail-closed on an unresolvable chapter →
   *  empty list. Omit for the editor/curation view (whole cast). */
  before_chapter_id?: string;
}

export interface EntitiesBrowseResponse {
  entities: Entity[];
  total: number;
  /** C8: set on the `semantic_query` vector path ("searched via X");
   *  null on the plain FTS/browse path OR when the project isn't
   *  indexed yet. */
  embedding_model?: string | null;
}

// ── C10 (C10-gap-report) — entity Gap Report ─────────────────────────
//
// ENTITY gaps: high-mention DISCOVERED entities with no glossary entry,
// from knowledge-service `find_gap_candidates()`. Distinct from
// lore-enrichment's attribute-dimension `detect-gaps` (a different
// feature in features/enrichment — do not conflate).
export interface GapReportParams {
  /** Mention-count floor; the FE threshold control feeds this straight
   *  to the BE query (pass-through). */
  min_mentions?: number;
  limit?: number;
}

export interface GapReportResponse {
  /** Discovered (unanchored) entities above the threshold. Each is a
   *  full Entity (status === 'discovered'), so the same StatusGlyph /
   *  promote machinery as the Entities tab applies. */
  gaps: Entity[];
  total: number;
  /** The active threshold, echoed by the BE — labels the report. */
  min_mentions: number;
}

// ── C18/C19 (G5) — GET /projects/{id}/subgraph ────────────────────────
//
// The read-only project subgraph for the C19 graph canvas. Mirrors the
// BE `Subgraph` model (relations.py): a lightweight node projection
// (identity + kind for colour + anchor_score/mention_count for sizing,
// NOT the full Entity — the canvas pulls full detail lazily via
// `getEntityDetail` on click) and `:RELATES_TO` edge projection. Raw
// nodes + edges; NO server-side layout (the canvas hand-rolls
// force/radial). `node_cap_hit` flags that the deterministic node cap
// trimmed the result so the canvas can offer expand / load-more.
export interface SubgraphNode {
  id: string;
  name: string;
  kind: string;
  anchor_score: number;
  mention_count: number;
  glossary_entity_id: string | null;
  /** W2 (G4) — set ONLY by the world rollup (`getWorldSubgraph`): the member
   *  project this node came from, so the FE can legend the per-book islands.
   *  `undefined`/`null` on the single-project subgraph (it never tags source). */
  source_project_id?: string | null;
}

export interface SubgraphEdge {
  id: string;
  source: string;
  target: string;
  predicate: string;
  confidence: number;
}

export interface SubgraphResponse {
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
  node_cap_hit: boolean;
}

export interface SubgraphParams {
  /** Traversal depth for ego-expansion (only applies when `center` is
   *  set). 1–3, clamped server-side. */
  hops?: number;
  /** Hard node cap (≤500, clamped server-side). Selected
   *  deterministically so expand / load-more is stable. */
  limit?: number;
  /** Optional entity id to ego-expand from — returns the `hops`-bounded
   *  neighbourhood instead of the project-wide top-N. Powers
   *  click-to-expand. */
  center?: string;
}

/**
 * K19d.4 EntityRelation wire shape. Mirrors the Relation Pydantic
 * projection on the BE: a :RELATES_TO edge with the two endpoint
 * names + kinds included so the detail panel can render
 * `(subject)-[predicate]->(object)` without a second round-trip.
 */
export interface EntityRelation {
  id: string;
  subject_id: string;
  object_id: string;
  predicate: string;
  confidence: number;
  source_event_ids: string[];
  source_chapter: string | null;
  valid_from: string | null;
  valid_until: string | null;
  pending_validation: boolean;
  created_at: string | null;
  updated_at: string | null;
  subject_name: string | null;
  subject_kind: string | null;
  object_name: string | null;
  object_kind: string | null;
}

export interface EntityDetail {
  entity: Entity;
  relations: EntityRelation[];
  relations_truncated: boolean;
  total_relations: number;
}

// ── T2.1 Cast & Codex — spoiler-windowed status + facts ───────────────

/** One entity's story-state at the windowed reading position. `from_order` is
 *  null when the entity has no recorded transition (defaults to `active`). */
export interface EntityStatusEntry {
  status: 'active' | 'gone';
  from_order: number | null;
}

/** Batch status for a project's cast, keyed by `Entity.id`. `window_available`
 *  is false when the chapter spoiler-window couldn't be resolved (fail-closed:
 *  everyone `active`, no history) — the codex shows a "reading position unknown"
 *  hint rather than implying a clean slate. */
export interface EntityStatusesResponse {
  statuses: Record<string, EntityStatusEntry>;
  window_available: boolean;
}

export type EntityFactType = 'decision' | 'preference' | 'milestone' | 'negation';

/** A known fact ABOUT an entity (decision/preference/…). Spoiler-windowed by
 *  `from_order` server-side. Mirrors the BE Fact projection (subset the codex
 *  renders). */
export interface EntityFact {
  id: string;
  type: EntityFactType;
  content: string;
  confidence: number;
  source_chapter: string | null;
  from_order: number | null;
}

export interface EntityFactsResponse {
  facts: EntityFact[];
  window_available: boolean;
}

export interface EntityStatusesParams {
  project_id: string;
  /** Window the status THROUGH this book chapter (resolved server-side). */
  before_chapter_id?: string;
  kind?: string;
}

// ── K19d γ-a — PATCH /entities/{id} body ──────────────────────────────

export interface EntityUpdatePayload {
  name?: string;
  kind?: string;
  /** Replaces the full list; not an append. Pass [] to clear. */
  aliases?: string[];
}

// ── T2.5 World Map — manual entity / relation authoring ──────────────

/** Create a user-authored entity (World Map "+ add place" / KG "+ New Entity").
 *  `kind` is one of the authorable closed set — see AUTHORABLE_ENTITY_KINDS in
 *  lib/entityKinds.ts (character|location|organization|concept|item), BE-enforced
 *  against the same gate. Idempotent on (name, kind) within the project. */
export interface CreateEntityPayload {
  project_id: string;
  name: string;
  kind: string;
}

/** Create a user-authored relation (World Map "link places"). 409 if either
 *  endpoint isn't the caller's entity; 422 on a self-loop. */
export interface CreateRelationPayload {
  subject_id: string;
  object_id: string;
  predicate: string;
}

// ── K19d γ-b — POST /entities/{id}/merge-into/{other} ────────────────

export interface EntityMergeResponse {
  target: Entity;
}

export type EntityMergeErrorCode =
  | 'same_entity'
  | 'entity_not_found'
  | 'entity_archived'
  | 'glossary_conflict'
  | 'unknown';

// ── K19e.2 — Timeline list ────────────────────────────────────────────

/**
 * K19e.2 — timeline event. Mirrors
 * services/knowledge-service/app/db/neo4j_repos/events.py::Event
 * one-to-one so a future BE field addition surfaces here without
 * breaking the union. Fields not yet rendered by the FE (chronological
 * _order, archived_at) are retained in the type so downstream cycles
 * can start using them without a fresh api.ts PR.
 */
export interface TimelineEvent {
  id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  canonical_title: string;
  summary: string | null;
  chapter_id: string | null;
  /**
   * C6 (D-K19e-β-01) — resolved chapter title denormalized in by
   * knowledge-service at response time via BookClient. Format:
   * `"Chapter N — Title"` (or `"Chapter N"` when the chapter has no
   * title set). `null` when the chapter isn't in book-service's
   * active set OR when book-service was unavailable — TimelineEventRow
   * falls back to the UUID-suffix short via `chapterShort()`.
   *
   * /review-impl L6: see `ExtractionJobWire.current_chapter_title`
   * for the rollout-window undefined-vs-null nuance. Same pattern
   * applies here — always consume via `event.chapter_title ??
   * fallback`.
   */
  chapter_title: string | null;
  event_order: number | null;
  chronological_order: number | null;
  /** C18 — in-story ISO date (partial precision: YYYY / YYYY-MM / YYYY-MM-DD).
   *  Present in the BE Event projection; declared here for the C-FE edit form. */
  event_date_iso: string | null;
  /** C18-DEF-01 — free-text narrative time hint (e.g. "the next morning"). */
  time_cue: string | null;
  participants: string[];
  confidence: number;
  source_types: string[];
  evidence_count: number;
  mention_count: number;
  archived_at: string | null;
  /** Phase B C2 — optimistic-concurrency version for user edits (If-Match).
   *  Pre-C2 events default to 1 on the BE read path. */
  version: number;
  created_at: string | null;
  updated_at: string | null;
  /** C14 (C14-importance-major-pivotal) — DERIVED salience the BE computes
   *  from existing signals (mention_count, participants, confidence); never
   *  a stored field, never re-extracted. `null` = ordinary/unbadged event
   *  (the common case — the long tail is NOT mislabeled). The rail badges
   *  only the non-null `major`/`pivotal` events. */
  importance: EventImportance | null;

  // ── KG-TL (timeline localization) — DERIVED, response-only Layer-2 fields ──
  // Populated ONLY when a reader language resolves on the read path; null/absent
  // on the canonical (no-language) response. Source `title`/`summary`/`time_cue`/
  // `participants` above stay source-language (Layer-1 untouched). The row
  // renders the `*_localized` value and an explicit "source" marker whenever the
  // matching `*_translated` flag is false (AC-T1 — never a silent mix).
  /** M2 — participant names in the reader language; same length+order as
   *  `participants`. Each slot is the translated name when the glossary had it,
   *  else the source name. Null when no reader language resolved. */
  participants_localized?: string[] | null;
  /** M2 — per-slot translated flag (parallel to `participants_localized`).
   *  false ⇒ that chip is showing the source name + gets a marker. */
  participants_translated?: boolean[] | null;
  /** M3 — summary in the reader language (COALESCE(cache, source)). */
  summary_localized?: string | null;
  /** M3 — true ⇒ `summary_localized` is a real translation; false ⇒ it is the
   *  source text awaiting the on-demand cache fill (render a "pending" marker). */
  summary_translated?: boolean | null;
  /** M3 — time_cue in the reader language (COALESCE(cache, source)). */
  time_cue_localized?: string | null;
  time_cue_translated?: boolean | null;
  /** M3 — title in the reader language (COALESCE(cache, source)). */
  title_localized?: string | null;
  title_translated?: boolean | null;
}

// C14 — closed importance enum mirroring the BE EVENT_IMPORTANCE tuple
// one-to-one. `major`/`pivotal` ONLY — no enum drift. The Event wire field
// is `EventImportance | null` (null = unbadged).
export const EVENT_IMPORTANCE = ['major', 'pivotal'] as const;
export type EventImportance = (typeof EVENT_IMPORTANCE)[number];

// C14 — timeline sort axis. `narrative` (default) = reading position
// (event_order); `chronological` = in-story chronology. Mirrors the BE
// TIMELINE_SORT_KEYS allowlist. Omitting it is back-compatible.
export const TIMELINE_SORT_KEYS = ['narrative', 'chronological'] as const;
export type TimelineSortBy = (typeof TIMELINE_SORT_KEYS)[number];

// D-K19e-α-03 — sort direction for the chosen axis. `asc` (default, back-compat)
// = earliest-first; `desc` = latest-first. Mirrors the BE TIMELINE_SORT_DIRECTIONS.
export const TIMELINE_SORT_DIRECTIONS = ['asc', 'desc'] as const;
export type TimelineSortDir = (typeof TIMELINE_SORT_DIRECTIONS)[number];

// ── Phase B C — relation + event correction payloads ─────────────────

export interface RelationCorrectPayload {
  old_relation_id: string;
  subject_id: string;
  predicate: string;
  object_id: string;
}

export interface EventUpdatePayload {
  title?: string;
  summary?: string;
  time_cue?: string;
  event_date_iso?: string;
}

export interface TimelineListParams {
  project_id?: string;
  /** Strict `event_order > after_order`. BE defers wall-clock date
   *  range (D-K19e-α-02) so narrative order is the only axis for MVP. */
  after_order?: number;
  before_order?: number;
  /** C10 (D-K19e-α-03): strict `chronological_order > after_chronological`.
   *  NULL-chrono events are excluded when either bound is set. */
  after_chronological?: number;
  before_chronological?: number;
  /** C10 (D-K19e-α-01): filter to events whose `participants` array
   *  contains the entity's display name, canonical_name, or any
   *  alias. BE resolves the id → participant-candidate list; cross-
   *  user / missing entity collapses to an empty timeline (no 404
   *  existence leak per KSA §6.4). */
  entity_id?: string;
  /** T2.1: spoiler-window the timeline THROUGH this book chapter (resolved
   *  server-side to a before_order ceiling). An explicit `before_order` wins. */
  before_chapter_id?: string;
  /** C14 (C14-narrative-order-sort): sort axis. `narrative` (default,
   *  back-compat when omitted) = reading position; `chronological` =
   *  in-story chronology. */
  sort_by?: TimelineSortBy;
  /** D-K19e-α-03: sort direction for the chosen `sort_by` axis. `asc` (default,
   *  back-compat) = earliest-first; `desc` = latest-first. */
  sort_dir?: TimelineSortDir;
  /** D-K19e-α-02: inclusive ISO date-range bounds (YYYY / YYYY-MM / YYYY-MM-DD)
   *  on `event_date_iso`. Events with NULL date are excluded when either is set. */
  event_date_from?: string;
  event_date_to?: string;
  /** #12: free-text search over event title + summary (case-insensitive
   *  substring, matched against SOURCE text). Empty/whitespace ignored. */
  q?: string;
  /** KG-TL — reader language for localizing the timeline (chapter heading +
   *  participant names + summary/time_cue/title). Sourced from the active UI
   *  language; the BE folds it to the primary subtag and resolves the stored
   *  reader-language pref when omitted. Omit ⇒ canonical source-language list. */
  language?: string;
  limit?: number;
  offset?: number;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  total: number;
}

// D-WORLD-TIMELINE-ROLLUP — the world timeline union (mirror of the W2 graph
// rollup). Events carry their own `project_id` so the FE can legend per book;
// `truncated` flags that the merged union exceeded the cap.
export interface WorldTimelineResponse {
  events: TimelineEvent[];
  total: number;
  truncated: boolean;
}

// ── K19e.5 — Drawer (passage) search ──────────────────────────────────

/**
 * K19e.5 — drawer search hit. Mirrors
 * services/knowledge-service/app/routers/public/drawers.py::DrawerSearchHit
 * (which drops ``user_id`` and the stored embedding from the public
 * wire). ``raw_score`` is cosine similarity in the [0, 1] practical
 * range — the card clamps to [0, 100]% for display.
 */
export interface DrawerSearchHit {
  id: string;
  project_id: string | null;
  source_type: string;
  source_id: string;
  chunk_index: number;
  text: string;
  is_hub: boolean;
  chapter_index: number | null;
  created_at: string | null;
  raw_score: number;
  /** KG-ML M7 (C12): the passage's source language (M1/M2). "unknown" for
   *  legacy untagged passages. Lets the card badge each hit's language. */
  source_lang?: string;
}

/** KG-ML M7 (C12): reader-language coverage for a drawer/raw search. Mirrors
 *  the BE ``language_coverage`` shape. ``note`` is null when coverage is full
 *  or no results; the FE shows it only when present. */
export interface LanguageCoverage {
  reader_lang: string;
  total: number;
  in_language: number;
  partial: boolean;
  note: string | null;
}

/** C8 (D-K19e-γa-01): closed enum mirrored from the BE's
 *  ``Literal['chapter','chat','glossary']``. Source of truth for the
 *  FE is this tuple — ``DrawerSourceType`` is derived from it, and
 *  consumers (filter pill row, pad helpers) iterate the tuple instead
 *  of hardcoding the 3-key set. Extending with a 4th type is a single
 *  edit here; BE Literal must be bumped in lockstep. */
export const DRAWER_SOURCE_TYPES = ['chapter', 'chat', 'glossary'] as const;
export type DrawerSourceType = (typeof DRAWER_SOURCE_TYPES)[number];

export interface DrawerSearchParams {
  project_id: string;
  query: string;
  limit?: number;
  /** C8: optional filter. Omit for "Any". */
  source_type?: DrawerSourceType;
  /** KG-ML M7 (C12): reader-language preference. Soft matched-first ordering
   *  (not a filter) + a coverage note. Omit for no preference. */
  language?: string;
}

export interface DrawerSearchResponse {
  hits: DrawerSearchHit[];
  /** ``null`` when the project has no embedding model configured
   *  (not-indexed-yet branch). ``string`` on any other outcome,
   *  including zero-hit live searches. */
  embedding_model: string | null;
  /** C8 (D-K19e-γa-01): facet counts per source_type. Always includes
   *  every key in the ``DrawerSourceType`` set (0 when absent) so the
   *  FE pill row stays layout-stable. Reflects project-wide totals
   *  filtered to the project's current embedding_model. */
  source_type_counts: Record<string, number>;
  /** KG-ML M7 (C12): reader-language coverage when ?language= was set; null
   *  otherwise (or when nothing to flag). */
  coverage?: LanguageCoverage | null;
  /** D-K19e-γa-02: per-search embedding cost transparency. Both null until
   *  the query was actually embedded, AND when the provider didn't report
   *  token usage (e.g. Ollama → "unknown", not "$0"). A genuinely-free
   *  self-hosted model reports tokens with a "0.00000000" cost. */
  embedding_prompt_tokens?: number | null;
  embedding_cost_usd?: string | null;
}

export type DrawerSearchErrorCode =
  | 'provider_error'
  | 'embedding_dim_mismatch'
  | 'unknown';

// ── Phase E2 — learning-service mining response shapes ─────────────────────

export interface MiningConfigQualityRow {
  genre: string | null;
  config_hash: string;
  run_count: number;
  succeeded: number;
  avg_entities_on_success: number | null;
  success_rate: number | null;
}

export interface MiningConfigQualityResponse {
  items: MiningConfigQualityRow[];
  exploration: MiningConfigQualityRow[];
}

export interface MiningModelMatrixRow {
  model_ref: string | null;
  scope: string | null;
  has_filter: boolean;
  run_count: number;
  succeeded: number;
  weighted_outcome: number | null;
}

export interface MiningModelMatrixResponse {
  items: MiningModelMatrixRow[];
}

export interface MiningDriftRow {
  target: string;
  base_default_version: string | null;
  affected_projects: number;
  distinct_after_values: number;
  drift_pattern: string;
  runs_with_outcome: number;
}

export interface MiningDefaultDriftResponse {
  items: MiningDriftRow[];
}

export interface MiningOutcomeRecomputeRow {
  run_id: string;
  project_id: string;
  pipeline_outcome: string | null;
  created_at: string;
  post_run_corrections: number;
  recomputed_outcome: string | null;
}

export interface MiningOutcomeRecomputeResponse {
  items: MiningOutcomeRecomputeRow[];
  total: number;
}

export interface DrawerSearchError extends Error {
  status?: number;
  errorCode: DrawerSearchErrorCode;
  /** BE forwards the provider's retryable hint on EmbeddingError so
   *  the FE can choose "Retry" vs "Fix config" messaging. Defaults
   *  to false when missing. */
  retryable: boolean;
  /** Server-supplied human-readable message if present. */
  detailMessage?: string;
}

/** Extract ``{error_code, message, retryable}`` from FastAPI's
 *  ``detail: {...}`` envelope. Consumers should ``switch`` on
 *  ``errorCode`` against the closed ``DrawerSearchErrorCode`` union. */
export function parseDrawersError(err: unknown): DrawerSearchError {
  const e = err as {
    message?: string;
    status?: number;
    body?: {
      detail?: {
        error_code?: string;
        message?: string;
        retryable?: boolean;
      };
    };
  };
  const detail = e.body?.detail;
  const code = (detail?.error_code ?? 'unknown') as DrawerSearchErrorCode;
  return Object.assign(new Error(e.message || 'drawer search failed'), {
    status: e.status,
    errorCode: code,
    retryable: Boolean(detail?.retryable ?? false),
    detailMessage: detail?.message,
  });
}

const BASE = '/v1/knowledge';
const LEARNING_BASE = '/v1/learning';

// D-K8-03: weak ETag format used by the knowledge-service routes.
const ifMatch = (version: number): Record<string, string> => ({
  'If-Match': `W/"${version}"`,
});

/**
 * D-K8-03: type-guarded helper for catching 412 Precondition Failed
 * errors from PATCH calls. The backend returns the CURRENT row in
 * the 412 body so callers can refresh their baseline in one
 * round-trip — no second GET needed.
 *
 * Usage:
 *   try { await knowledgeApi.updateProject(...) }
 *   catch (err) {
 *     if (isVersionConflict<Project>(err)) {
 *       // err.current is the fresh Project — update state and retry.
 *     }
 *   }
 */
export function isVersionConflict<T>(
  err: unknown,
): err is Error & { status: 412; current: T } {
  if (!(err instanceof Error)) return false;
  const e = err as Error & { status?: number; body?: unknown };
  if (e.status !== 412) return false;
  if (e.body == null || typeof e.body !== 'object') return false;
  // Attach `current` once for convenience — idempotent.
  (e as unknown as { current: T }).current = e.body as T;
  return true;
}

// Mirrors the helper in src/api.ts — needed for raw `fetch()` calls
// (the export endpoint streams a file and can't go through apiJson).
// Keeping this local matches the pattern in src/features/books/api.ts.
const apiBase = () => (import.meta.env.VITE_API_BASE as string | undefined) || '';

export const knowledgeApi = {
  // ── projects ───────────────────────────────────────────────────────────

  listProjects(
    params: ProjectListParams,
    token: string,
  ): Promise<ProjectListResponse> {
    const qs = new URLSearchParams();
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.cursor) qs.set('cursor', params.cursor);
    if (params.include_archived) qs.set('include_archived', 'true');
    if (params.book_id) qs.set('book_id', params.book_id);
    // C7-followup (KN-7): server-side narrowing. Only send a non-empty
    // search so a cleared box reverts to the unfiltered list.
    if (params.search) qs.set('search', params.search);
    if (params.sort_by) qs.set('sort_by', params.sort_by);
    if (params.sort_dir) qs.set('sort_dir', params.sort_dir);
    if (params.status) qs.set('status', params.status);
    const q = qs.toString();
    return apiJson<ProjectListResponse>(
      `${BASE}/projects${q ? `?${q}` : ''}`,
      { token },
    );
  },

  getProject(projectId: string, token: string): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects/${projectId}`, { token });
  },

  createProject(
    payload: ProjectCreatePayload,
    token: string,
  ): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  updateProject(
    projectId: string,
    payload: ProjectUpdatePayload,
    token: string,
    expectedVersion: number,
  ): Promise<Project> {
    // D-K8-03: If-Match is strictly required for PATCH. The backend
    // returns 428 if the header is missing, 412 if it's stale.
    return apiJson<Project>(`${BASE}/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
      headers: ifMatch(expectedVersion),
    });
  },

  // B2-B/C — per-novel extraction-config tuning. PUT-REPLACE: the caller must
  // send the COMPLETE config (read-modify-write off project.extraction_config),
  // since an omitted section is dropped. If-Match strictly required (428 / 412).
  updateExtractionConfig(
    projectId: string,
    payload: ExtractionConfigPayload,
    token: string,
    expectedVersion: number,
  ): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects/${projectId}/extraction-config`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      token,
      headers: ifMatch(expectedVersion),
    });
  },

  archiveProject(projectId: string, token: string): Promise<Project> {
    return apiJson<Project>(`${BASE}/projects/${projectId}/archive`, {
      method: 'POST',
      token,
    });
  },

  deleteProject(projectId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/projects/${projectId}`, {
      method: 'DELETE',
      token,
    });
  },

  // ── summaries ──────────────────────────────────────────────────────────

  listSummaries(token: string): Promise<SummariesListResponse> {
    return apiJson<SummariesListResponse>(`${BASE}/summaries`, { token });
  },

  updateGlobalSummary(
    payload: SummaryUpdatePayload,
    token: string,
    expectedVersion: number | null,
  ): Promise<Summary> {
    // D-K8-03: If-Match is required for update path. null means
    // "first save" — no prior row, so no version to match. The
    // backend allows it; subsequent saves must send a version.
    return apiJson<Summary>(`${BASE}/summaries/global`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
      headers: expectedVersion != null ? ifMatch(expectedVersion) : undefined,
    });
  },

  updateProjectSummary(
    projectId: string,
    payload: SummaryUpdatePayload,
    token: string,
    expectedVersion: number | null,
  ): Promise<Summary> {
    return apiJson<Summary>(`${BASE}/projects/${projectId}/summary`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      token,
      headers: expectedVersion != null ? ifMatch(expectedVersion) : undefined,
    });
  },

  // ── D-K8-01: global summary version history ────────────────────────────

  listGlobalSummaryVersions(
    token: string,
    limit = 50,
  ): Promise<SummaryVersionListResponse> {
    return apiJson<SummaryVersionListResponse>(
      `${BASE}/summaries/global/versions?limit=${limit}`,
      { token },
    );
  },

  getGlobalSummaryVersion(
    version: number,
    token: string,
  ): Promise<SummaryVersion> {
    return apiJson<SummaryVersion>(
      `${BASE}/summaries/global/versions/${version}`,
      { token },
    );
  },

  rollbackGlobalSummary(
    version: number,
    token: string,
    expectedVersion: number,
  ): Promise<Summary> {
    return apiJson<Summary>(
      `${BASE}/summaries/global/versions/${version}/rollback`,
      {
        method: 'POST',
        token,
        headers: ifMatch(expectedVersion),
      },
    );
  },

  // ── user data (GDPR) ───────────────────────────────────────────────────

  // The /export endpoint returns JSON with a Content-Disposition
  // attachment header. We fetch it directly (not apiJson) so the
  // browser can trigger the download via Blob + object URL.
  async exportUserData(token: string): Promise<{ blob: Blob; filename: string }> {
    const res = await fetch(`${apiBase()}${BASE}/user-data/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw Object.assign(new Error(text || res.statusText), {
        status: res.status,
      });
    }
    const blob = await res.blob();
    // Parse filename from Content-Disposition; fall back to a default.
    const disp = res.headers.get('Content-Disposition') ?? '';
    const match = /filename="([^"]+)"/.exec(disp);
    const filename = match?.[1] ?? 'loreweave-knowledge-export.json';
    return { blob, filename };
  },

  deleteAllUserData(token: string): Promise<UserDataDeleteResponse> {
    return apiJson<UserDataDeleteResponse>(`${BASE}/user-data`, {
      method: 'DELETE',
      token,
    });
  },

  // ── T2-close-1b-FE — K17.9 benchmark status ─────────────────────────
  /**
   * Fetch the latest K17.9 benchmark run for a project, optionally
   * scoped to a specific embedding model. Returns `has_run=false`
   * (200) when nothing has been benchmarked yet — not a 404, so the
   * FE can render a neutral "Run benchmark" badge instead of an error.
   *
   * Errors (404 = cross-user / nonexistent project) are thrown via
   * apiJson so the caller can choose to degrade silently (show no
   * badge) rather than alarming the user over a transient ownership
   * issue.
   */
  getBenchmarkStatus(
    projectId: string,
    embeddingModel: string | null,
    token: string,
  ): Promise<BenchmarkStatus> {
    const qs = new URLSearchParams();
    if (embeddingModel) qs.set('embedding_model', embeddingModel);
    const q = qs.toString();
    return apiJson<BenchmarkStatus>(
      `${BASE}/projects/${projectId}/benchmark-status${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── C12b-b — K17.9 on-demand benchmark run (sync) ────────────────────
  /**
   * POST /v1/knowledge/projects/{id}/benchmark-run — runs the K17.9
   * golden-set harness synchronously (typical 15-60s). `runs` is
   * optional; BE defaults to 3 and clamps to [1..5].
   *
   * Throws on non-2xx via apiJson. Caller should parse `err.body.detail`
   * for `error_code`. Error codes from C12b-a BE:
   *   - 404 project not found (cross-user / missing)
   *   - 409 `no_embedding_model` / `unknown_embedding_model` /
   *         `not_benchmark_project` / `benchmark_already_running`
   *   - 502 `embedding_provider_flake` (fixture load incomplete —
   *         provider embedded fewer entities than the golden set;
   *         BE refuses to persist a false-negative row)
   */
  runBenchmark(
    projectId: string,
    runs: number | undefined,
    token: string,
  ): Promise<BenchmarkRunResponse> {
    return apiJson<BenchmarkRunResponse>(
      `${BASE}/projects/${projectId}/benchmark-run`,
      {
        method: 'POST',
        body: JSON.stringify(runs !== undefined ? { runs } : {}),
        token,
      },
    );
  },

  // ── K19a.4 — extraction lifecycle ───────────────────────────────────────

  listExtractionJobs(projectId: string, token: string): Promise<ExtractionJobWire[]> {
    return apiJson<ExtractionJobWire[]>(
      `${BASE}/projects/${projectId}/extraction/jobs`,
      { token },
    );
  },

  // T4.1 — the canon-growth delta from the latest completed extraction job.
  getFlywheel(projectId: string, token: string): Promise<FlywheelDeltaWire> {
    return apiJson<FlywheelDeltaWire>(
      `${BASE}/projects/${projectId}/flywheel`,
      { token },
    );
  },

  // K19b.1 + C11 — user-scoped cross-project list, grouped by status,
  // with cursor pagination.
  // Powers the Jobs tab (no per-project fanout). BE validates
  // status_group (422 on missing/invalid), clamps limit to [1, 200],
  // and returns 422 on a malformed cursor.
  listAllJobs(
    params: {
      statusGroup: 'active' | 'history';
      limit?: number;
      cursor?: string;
    },
    token: string,
  ): Promise<ExtractionJobsPageResponse> {
    const qs = new URLSearchParams({ status_group: params.statusGroup });
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.cursor != null) qs.set('cursor', params.cursor);
    return apiJson<ExtractionJobsPageResponse>(
      `${BASE}/extraction/jobs?${qs.toString()}`,
      { token },
    );
  },

  getGraphStats(projectId: string, token: string): Promise<GraphStatsResponse> {
    return apiJson<GraphStatsResponse>(
      `${BASE}/projects/${projectId}/graph-stats`,
      { token },
    );
  },

  estimateExtraction(
    projectId: string,
    payload: EstimateExtractionPayload,
    token: string,
  ): Promise<CostEstimate> {
    return apiJson<CostEstimate>(
      `${BASE}/projects/${projectId}/extraction/estimate`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  startExtraction(
    projectId: string,
    payload: ExtractionStartPayload,
    token: string,
  ): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/start`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  // C13 — auto-pin suggestion data for the build-wizard Step-2 banner.
  getGlossaryEntityStats(
    projectId: string,
    token: string,
  ): Promise<GlossaryEntityStatsResponse> {
    return apiJson<GlossaryEntityStatsResponse>(
      `${BASE}/projects/${encodeURIComponent(projectId)}/glossary-entity-stats`,
      { method: 'GET', token },
    );
  },

  pauseExtraction(projectId: string, token: string): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/pause`,
      { method: 'POST', token },
    );
  },

  resumeExtraction(projectId: string, token: string): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/resume`,
      { method: 'POST', token },
    );
  },

  cancelExtraction(projectId: string, token: string): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/projects/${projectId}/extraction/cancel`,
      { method: 'POST', token },
    );
  },

  // C7 raise-cap (KN-7) — change a running/paused job's parallel-LLM
  // concurrency cap IN-FLIGHT. The worker re-reads it each poll cycle, so
  // the next chapter window picks up the new cap. Bounds 1–64 (BE 422s
  // outside that); 409 if the job is terminal.
  updateJobConcurrency(
    jobId: string,
    concurrencyLevel: number,
    token: string,
  ): Promise<ExtractionJobWire> {
    return apiJson<ExtractionJobWire>(
      `${BASE}/extraction/jobs/${encodeURIComponent(jobId)}/concurrency`,
      {
        method: 'PATCH',
        body: JSON.stringify({ concurrency_level: concurrencyLevel }),
        token,
      },
    );
  },

  deleteGraph(projectId: string, token: string): Promise<DeleteGraphResponse> {
    return apiJson<DeleteGraphResponse>(
      `${BASE}/projects/${projectId}/extraction/graph`,
      { method: 'DELETE', token },
    );
  },

  // bug #14 — destructive guard. Without `confirm`, the BE returns a
  // RebuildWarning preview (node counts) and deletes nothing; the FE shows a
  // typed confirmation, then re-calls with `confirm=true` to commit.
  rebuildGraph(
    projectId: string,
    payload: RebuildPayload,
    token: string,
    confirm = false,
  ): Promise<ExtractionJobWire | RebuildWarning> {
    return apiJson<ExtractionJobWire | RebuildWarning>(
      `${BASE}/projects/${projectId}/extraction/rebuild${confirm ? '?confirm=true' : ''}`,
      { method: 'POST', body: JSON.stringify(payload), token },
    );
  },

  // K19a.6 — PUT /embedding-model. The BE requires `?confirm=true` for
  // the destructive path (deletes graph + switches model + disables).
  // Without `confirm`, BE returns a warning preview with
  // `action_required: 'confirm'`. Callers typically invoke twice: once
  // to preview (or skip that and go straight to confirm), once to
  // commit. Same-model requests return a third no-op shape.
  //
  // Prior signature returned Promise<Project> which was always wrong —
  // BE never returns a Project from this endpoint. K19a.5 callers
  // weren't calling this; K19a.6 dialog is the first real consumer.
  updateEmbeddingModel(
    projectId: string,
    embeddingModel: string,
    token: string,
    opts?: { confirm?: boolean },
  ): Promise<ChangeEmbeddingModelResponse> {
    const qs = opts?.confirm ? '?confirm=true' : '';
    return apiJson<ChangeEmbeddingModelResponse>(
      `${BASE}/projects/${projectId}/embedding-model${qs}`,
      {
        method: 'PUT',
        body: JSON.stringify({ embedding_model: embeddingModel }),
        token,
      },
    );
  },

  // ── K19c.4 — user-scope entities ───────────────────────────────────────

  listMyEntities(
    params: { scope: 'global'; limit?: number },
    token: string,
  ): Promise<UserEntitiesResponse> {
    const qs = new URLSearchParams({ scope: params.scope });
    if (params.limit != null) qs.set('limit', String(params.limit));
    return apiJson<UserEntitiesResponse>(
      `${BASE}/me/entities?${qs.toString()}`,
      { token },
    );
  },

  archiveMyEntity(entityId: string, token: string): Promise<void> {
    // BE returns 204 No Content on success; apiJson handles empty-body
    // responses by resolving with `undefined`.
    return apiJson<void>(`${BASE}/me/entities/${entityId}`, {
      method: 'DELETE',
      token,
    });
  },

  // D-KG-ENTITY-RESTORE (S7) — the inverse of archiveMyEntity, so a hidden
  // entity can come back (archive is otherwise a one-way trap). 204 on success.
  restoreMyEntity(entityId: string, token: string): Promise<void> {
    return apiJson<void>(`${BASE}/me/entities/${entityId}/restore`, {
      method: 'POST',
      token,
    });
  },

  // ── K19b.8 — extraction job logs ───────────────────────────────────────

  listJobLogs(
    jobId: string,
    params: { sinceLogId?: number; limit?: number },
    token: string,
  ): Promise<JobLogsResponse> {
    const qs = new URLSearchParams();
    if (params.sinceLogId != null) qs.set('since_log_id', String(params.sinceLogId));
    if (params.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiJson<JobLogsResponse>(
      `${BASE}/extraction/jobs/${jobId}/logs${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // Studio Quality tab (`quality-canon`) / D-KG-CANON-FLAG-REVIEW-UI — every
  // judge-confirmed canon contradiction flagged during KG extraction for this
  // project, newest first.
  listCanonFlags(projectId: string, token: string, limit?: number): Promise<CanonFlagsResponse> {
    const q = limit != null ? `?limit=${limit}` : '';
    return apiJson<CanonFlagsResponse>(`${BASE}/extraction/projects/${projectId}/canon-flags${q}`, { token });
  },

  // ── K19b.6 — user-wide costs & budget ──────────────────────────────────

  getUserCosts(token: string): Promise<UserCostSummary> {
    return apiJson<UserCostSummary>(`${BASE}/costs`, { token });
  },

  setUserBudget(
    payload: SetUserBudgetPayload,
    token: string,
  ): Promise<SetUserBudgetResponse> {
    return apiJson<SetUserBudgetResponse>(`${BASE}/me/budget`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      token,
    });
  },

  // K19a.6 — non-destructive POST /extraction/disable. Preserves the
  // Neo4j graph; contrasts with deleteGraph (destructive) and
  // updateEmbeddingModel (destructive).
  disableExtraction(
    projectId: string,
    token: string,
  ): Promise<DisableExtractionResponse> {
    return apiJson<DisableExtractionResponse>(
      `${BASE}/projects/${projectId}/extraction/disable`,
      { method: 'POST', token },
    );
  },

  // ── K20α — summary regeneration ───────────────────────────────────────

  regenerateGlobalBio(
    body: RegenerateRequest,
    token: string,
  ): Promise<RegenerateResponse> {
    return apiJson<RegenerateResponse>(`${BASE}/me/summary/regenerate`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  // ── K19d — entities browse + detail ──────────────────────────────────

  listEntities(
    params: EntitiesListParams,
    token: string,
  ): Promise<EntitiesBrowseResponse> {
    const qs = new URLSearchParams();
    if (params.project_id != null) qs.set('project_id', params.project_id);
    if (params.kind != null) qs.set('kind', params.kind);
    if (params.search != null) qs.set('search', params.search);
    if (params.semantic_query != null)
      qs.set('semantic_query', params.semantic_query);
    if (params.status != null) qs.set('status', params.status);
    if (params.sort_by != null) qs.set('sort_by', params.sort_by);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.offset != null) qs.set('offset', String(params.offset));
    // W11 reader spoiler window — restricts the list to entities met by this chapter.
    if (params.before_chapter_id != null)
      qs.set('before_chapter_id', params.before_chapter_id);
    const q = qs.toString();
    return apiJson<EntitiesBrowseResponse>(
      `${BASE}/entities${q ? `?${q}` : ''}`,
      { token },
    );
  },

  getEntityDetail(entityId: string, token: string): Promise<EntityDetail> {
    return apiJson<EntityDetail>(
      `${BASE}/entities/${encodeURIComponent(entityId)}`,
      { token },
    );
  },

  // ── C10 (C10-gap-report) — GET /projects/{id}/gaps ──────────────────
  //
  // Thin pass-through to find_gap_candidates: high-mention DISCOVERED
  // entities with no glossary entry. `min_mentions` + `limit` flow to
  // the BE query. Project is route-scoped (G6) — passed positionally,
  // never via a select-box.
  getProjectGaps(
    projectId: string,
    params: GapReportParams,
    token: string,
  ): Promise<GapReportResponse> {
    const qs = new URLSearchParams();
    if (params.min_mentions != null)
      qs.set('min_mentions', String(params.min_mentions));
    if (params.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiJson<GapReportResponse>(
      `${BASE}/projects/${encodeURIComponent(projectId)}/gaps${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── C19 (G5) — GET /projects/{id}/subgraph ──────────────────────────
  //
  // Read-only project subgraph for the graph canvas. Thin client over
  // C18's endpoint: `center` ego-expands (with `hops`), no center =
  // project-wide top-N. `limit` is the node cap. Project route-scoped
  // (G6). No new BE — C18 owns this endpoint.
  getProjectSubgraph(
    projectId: string,
    params: SubgraphParams,
    token: string,
  ): Promise<SubgraphResponse> {
    const qs = new URLSearchParams();
    if (params.hops != null) qs.set('hops', String(params.hops));
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.center != null) qs.set('center', params.center);
    const q = qs.toString();
    return apiJson<SubgraphResponse>(
      `${BASE}/projects/${encodeURIComponent(projectId)}/subgraph${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── W2 (G4) — GET /worlds/{id}/subgraph (world rollup) ────────────────
  //
  // The world's canon rollup: a UNION of each member book's C18 subgraph +
  // the world-level (bible) project, merged server-side into one
  // `{nodes, edges, node_cap_hit}` payload (same Subgraph wire as the
  // per-project view). Nodes carry `source_project_id` so the FE can legend
  // the per-book islands. Owner-scoped server-side (a world the caller
  // doesn't own → 404). No `center`/expand — the union is flat (the per-book
  // graphs are disconnected components by design). 503 if book-service (the
  // membership source) is unavailable.
  getWorldSubgraph(
    worldId: string,
    params: { limit?: number },
    token: string,
  ): Promise<SubgraphResponse> {
    const qs = new URLSearchParams();
    if (params.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiJson<SubgraphResponse>(
      `${BASE}/worlds/${encodeURIComponent(worldId)}/subgraph${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── T2.5 World Map — manual authoring ────────────────────────────────

  /** Create a user-authored entity (e.g. a World Map place). 201. */
  createEntity(payload: CreateEntityPayload, token: string): Promise<Entity> {
    return apiJson<Entity>(`${BASE}/entities`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  /** Create a user-authored relation between two of the caller's entities. 201;
   *  409 if an endpoint isn't the caller's; 422 on a self-loop. */
  createRelation(payload: CreateRelationPayload, token: string): Promise<EntityRelation> {
    return apiJson<EntityRelation>(`${BASE}/relations`, {
      method: 'POST',
      body: JSON.stringify(payload),
      token,
    });
  },

  // ── K19d γ-a — PATCH /entities/{id} ──────────────────────────────────

  updateEntity(
    entityId: string,
    body: EntityUpdatePayload,
    ifMatchVersion: number,
    token: string,
  ): Promise<Entity> {
    return apiJson<Entity>(
      `${BASE}/entities/${encodeURIComponent(entityId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
        token,
        // C9 (D-K19d-γa-01): strict If-Match — BE 428s without it.
        headers: ifMatch(ifMatchVersion),
      },
    );
  },

  // C9 (D-K19d-γa-02) — POST /entities/{id}/unlock
  unlockEntity(entityId: string, token: string): Promise<Entity> {
    return apiJson<Entity>(
      `${BASE}/entities/${encodeURIComponent(entityId)}/unlock`,
      {
        method: 'POST',
        token,
      },
    );
  },

  // ── C9 (C9-promote-flow) — POST /entities/{id}/promote ───────────────
  //
  // Promote a DISCOVERED entity into the glossary curation flywheel. The
  // BE orchestrates the two-call flow server-side: (1) create a glossary
  // DRAFT (status=draft, tag `ai-suggested`) and (2) anchor the entity
  // (glossary_entity_id + anchor_score=1.0). Returns the now-canonical
  // Entity. Errors carry a structured `detail.error_code`:
  //   - 404                          — entity missing / cross-user
  //   - 409 `already_anchored`       — entity already canonical (no re-promote)
  //   - 422 `no_book`                — project has no linked book
  //   - 502 `glossary_draft_failed`  — draft-create failed (NOT anchored)
  //   - 502 `anchor_failed`          — draft created but anchor missed
  //                                    (retry is safe; no duplicate draft)
  promoteEntity(entityId: string, token: string): Promise<Entity> {
    return apiJson<Entity>(
      `${BASE}/entities/${encodeURIComponent(entityId)}/promote`,
      {
        method: 'POST',
        token,
      },
    );
  },

  // ── C9 — glossary context-pin toggle (is_pinned_for_context) ─────────
  //
  // POST/DELETE /v1/glossary/books/{book_id}/entities/{glossary_entity_id}/pin
  // — idempotent toggle of the glossary entity's `is_pinned_for_context`
  // flag (the entity-detail "unpin" control). Only meaningful for a
  // canonical knowledge entity (it has a `glossary_entity_id`); the FE
  // gates the control on that. 204 No Content on success.
  setGlossaryEntityPinned(
    bookId: string,
    glossaryEntityId: string,
    pinned: boolean,
    token: string,
  ): Promise<void> {
    return apiJson<void>(
      `/v1/glossary/books/${encodeURIComponent(bookId)}/entities/${encodeURIComponent(
        glossaryEntityId,
      )}/pin`,
      {
        method: pinned ? 'POST' : 'DELETE',
        token,
      },
    );
  },

  // ── K19d γ-b — POST /entities/{id}/merge-into/{other} ────────────────

  mergeEntityInto(
    sourceId: string,
    targetId: string,
    token: string,
  ): Promise<EntityMergeResponse> {
    return apiJson<EntityMergeResponse>(
      `${BASE}/entities/${encodeURIComponent(sourceId)}/merge-into/${encodeURIComponent(targetId)}`,
      {
        method: 'POST',
        token,
      },
    );
  },

  // ── Phase B C — relation corrections ─────────────────────────────────

  getRelation(relationId: string, token: string): Promise<EntityRelation> {
    return apiJson<EntityRelation>(
      `${BASE}/relations/${encodeURIComponent(relationId)}`,
      { token },
    );
  },

  /** Mark a relation wrong → soft-invalidate (spurious-drop correction). */
  invalidateRelation(relationId: string, token: string): Promise<EntityRelation> {
    return apiJson<EntityRelation>(
      `${BASE}/relations/${encodeURIComponent(relationId)}/invalidate`,
      { method: 'POST', token },
    );
  },

  /** Fix a relation: invalidate the old edge + recreate the corrected one
   *  (predicate-fix correction). Returns the live (resurrected) edge. */
  correctRelation(
    body: RelationCorrectPayload,
    token: string,
  ): Promise<EntityRelation> {
    return apiJson<EntityRelation>(`${BASE}/relations/correct`, {
      method: 'POST',
      body: JSON.stringify(body),
      token,
    });
  },

  // ── Phase B C — event corrections ────────────────────────────────────

  updateEvent(
    eventId: string,
    body: EventUpdatePayload,
    ifMatchVersion: number,
    token: string,
  ): Promise<TimelineEvent> {
    return apiJson<TimelineEvent>(
      `${BASE}/events/${encodeURIComponent(eventId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
        token,
        // C2: strict If-Match — BE 428s without it.
        headers: ifMatch(ifMatchVersion),
      },
    );
  },

  /** Soft-archive an event (user "delete"). 204 No Content. */
  archiveEvent(eventId: string, token: string): Promise<void> {
    return apiJson<void>(
      `${BASE}/events/${encodeURIComponent(eventId)}`,
      { method: 'DELETE', token },
    );
  },

  // ── Phase E2 — learning-service mining ───────────────────────────────────

  miningConfigQuality(
    token: string,
    params?: { genre?: string; limit?: number },
  ): Promise<MiningConfigQualityResponse> {
    const qs = new URLSearchParams();
    if (params?.genre) qs.set('genre', params.genre);
    if (params?.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiJson<MiningConfigQualityResponse>(
      `${LEARNING_BASE}/mining/config-quality${q ? `?${q}` : ''}`,
      { token },
    );
  },

  miningModelMatrix(
    token: string,
    params?: { scope?: string },
  ): Promise<MiningModelMatrixResponse> {
    const qs = new URLSearchParams();
    if (params?.scope) qs.set('scope', params.scope);
    const q = qs.toString();
    return apiJson<MiningModelMatrixResponse>(
      `${LEARNING_BASE}/mining/model-matrix${q ? `?${q}` : ''}`,
      { token },
    );
  },

  miningDefaultDrift(
    token: string,
    params?: { target?: string; base_default_version?: string },
  ): Promise<MiningDefaultDriftResponse> {
    const qs = new URLSearchParams();
    if (params?.target) qs.set('target', params.target);
    if (params?.base_default_version) qs.set('base_default_version', params.base_default_version);
    const q = qs.toString();
    return apiJson<MiningDefaultDriftResponse>(
      `${LEARNING_BASE}/mining/default-drift${q ? `?${q}` : ''}`,
      { token },
    );
  },

  miningOutcomeRecompute(
    token: string,
    params?: { project_id?: string; window_days?: number; limit?: number; offset?: number },
  ): Promise<MiningOutcomeRecomputeResponse> {
    const qs = new URLSearchParams();
    if (params?.project_id) qs.set('project_id', params.project_id);
    if (params?.window_days != null) qs.set('window_days', String(params.window_days));
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<MiningOutcomeRecomputeResponse>(
      `${LEARNING_BASE}/mining/outcome-recompute${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── K19e.2 — GET /v1/knowledge/timeline ──────────────────────────────

  listTimeline(
    params: TimelineListParams,
    token: string,
  ): Promise<TimelineResponse> {
    const qs = new URLSearchParams();
    if (params.project_id != null) qs.set('project_id', params.project_id);
    if (params.after_order != null)
      qs.set('after_order', String(params.after_order));
    if (params.before_order != null)
      qs.set('before_order', String(params.before_order));
    if (params.after_chronological != null)
      qs.set('after_chronological', String(params.after_chronological));
    if (params.before_chronological != null)
      qs.set('before_chronological', String(params.before_chronological));
    if (params.entity_id != null) qs.set('entity_id', params.entity_id);
    if (params.before_chapter_id != null)
      qs.set('before_chapter_id', params.before_chapter_id);
    if (params.sort_by != null) qs.set('sort_by', params.sort_by);
    if (params.sort_dir != null) qs.set('sort_dir', params.sort_dir);
    if (params.event_date_from != null)
      qs.set('event_date_from', params.event_date_from);
    if (params.event_date_to != null)
      qs.set('event_date_to', params.event_date_to);
    if (params.q && params.q.trim()) qs.set('q', params.q.trim());
    if (params.language) qs.set('language', params.language);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.offset != null) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiJson<TimelineResponse>(
      `${BASE}/timeline${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── D-WORLD-TIMELINE-ROLLUP — GET /worlds/{id}/timeline ──────────────
  //
  // The world's canon timeline rollup: a UNION of each member book's timeline +
  // the world-level (bible) project, merged + re-sorted server-side. Same
  // owner-scoping / 404 / 503 semantics as the world subgraph. Read-only.
  getWorldTimeline(
    worldId: string,
    params: { sort_by?: TimelineSortBy; limit?: number },
    token: string,
  ): Promise<WorldTimelineResponse> {
    const qs = new URLSearchParams();
    if (params.sort_by) qs.set('sort_by', params.sort_by);
    if (params.limit != null) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiJson<WorldTimelineResponse>(
      `${BASE}/worlds/${encodeURIComponent(worldId)}/timeline${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── T2.1 Cast & Codex ────────────────────────────────────────────────

  /** Batch story-state (active|gone) for a project's cast, windowed to the
   *  current chapter. Project-scoped (no client id list). */
  getEntityStatuses(
    params: EntityStatusesParams,
    token: string,
  ): Promise<EntityStatusesResponse> {
    const qs = new URLSearchParams({ project_id: params.project_id });
    if (params.before_chapter_id != null)
      qs.set('before_chapter_id', params.before_chapter_id);
    if (params.kind != null) qs.set('kind', params.kind);
    return apiJson<EntityStatusesResponse>(
      `${BASE}/entities/statuses?${qs.toString()}`,
      { token },
    );
  },

  /** The known-facts list ABOUT one entity, spoiler-windowed by chapter. */
  getEntityFacts(
    entityId: string,
    params: { before_chapter_id?: string },
    token: string,
  ): Promise<EntityFactsResponse> {
    const qs = new URLSearchParams();
    if (params.before_chapter_id != null)
      qs.set('before_chapter_id', params.before_chapter_id);
    const q = qs.toString();
    return apiJson<EntityFactsResponse>(
      `${BASE}/entities/${encodeURIComponent(entityId)}/facts${q ? `?${q}` : ''}`,
      { token },
    );
  },

  // ── K19e.5 — GET /v1/knowledge/drawers/search ────────────────────────

  searchDrawers(
    params: DrawerSearchParams,
    token: string,
  ): Promise<DrawerSearchResponse> {
    const qs = new URLSearchParams();
    qs.set('project_id', params.project_id);
    qs.set('query', params.query);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.source_type != null) qs.set('source_type', params.source_type);
    if (params.language) qs.set('language', params.language);
    return apiJson<DrawerSearchResponse>(
      `${BASE}/drawers/search?${qs.toString()}`,
      { token },
    );
  },
};

// Re-exported for consumers that need them alongside the wire types.
export type { ExtractionJobStatus };
