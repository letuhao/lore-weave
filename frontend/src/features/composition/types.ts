// LOOM Composition (M8) — FE types mirroring the composition-service contract.

export type Work = {
  project_id: string;
  user_id: string;
  book_id: string;
  active_template_id: string | null;
  status: 'active' | 'archived';
  settings: Record<string, unknown>;
  version: number;
  // C16 — surrogate PK (null project_id = lazy greenfield Work awaiting backfill).
  // Optional in the FE type so pre-C16/C23 callers degrade gracefully.
  id?: string | null;
  // C23 (dị bản M0) — a DERIVATIVE Work points at the SOURCE Work it diverges
  // from (in-DB self-ref on the surrogate id) at a chapter-level `branch_point`
  // (G3). Both null for a greenfield Work. The studio banner (C24) keys off
  // `source_work_id` to know it's editing a dị bản.
  source_work_id?: string | null;
  branch_point?: number | null;
};

// ── C24 (dị bản M0) — divergence wizard / derivative spawn ────────────────────
// Mirrors composition-service DeriveBody (works.py). The 3 UX §7.1 taxonomies all
// reduce to `branch_point` + optional `pov_anchor` + `entity_override[]` + added
// `canon_rule[]` (LOCKED M0 override scope = entity fields + canon rules only).
export type DivergenceTaxonomy = 'pov_shift' | 'character_transform' | 'au';

// One entity-FIELD override (M0 scope — relationship/event overrides DEFERRED).
// `overridden_fields` is the field→value JSON delta the writer authored.
export type EntityOverride = {
  target_entity_id: string;
  overridden_fields: Record<string, unknown>;
};

export type DivergenceSpec = {
  taxonomy: DivergenceTaxonomy;
  pov_anchor: string | null;
  canon_rule: string[];
};

export type DeriveBody = {
  branch_point: number | null;
  divergence: DivergenceSpec;
  entity_overrides: EntityOverride[];
};

export type WorkResolution = {
  status: 'found' | 'candidates' | 'unmarked_single' | 'unmarked_candidates' | 'none' | 'unavailable';
  work: Work | null;
  candidates: Work[];
  book_project_id: string | null;
  book_project_ids: string[];
};

// T0.1 — narrative-thread (promise/foreshadow) ledger row. Advisory (D4); the
// `open` set is the author's unpaid-promise debt. Mirrors composition-service
// NarrativeThread (app/db/models.py).
export type ThreadKind = 'promise' | 'foreshadow' | 'question' | 'mice_thread';
export type ThreadStatus = 'open' | 'progressing' | 'paid' | 'dropped';
export type NarrativeThread = {
  id: string;
  project_id: string;
  user_id: string;
  kind: ThreadKind;
  status: ThreadStatus;
  opened_at_node: string | null;
  payoff_node: string | null;
  priority: number;
  summary: string;
  version: number;
};

// ── A3 decompose planner (cycle 13) ──────────────────────────────────────────
// T1.2 Beat Sheet — a template beat: a `key` (joins to node.beat_role) + its
// structural `purpose`. Mirrors the BE StructureTemplate.beats (plan.py).
export type Beat = { key: string; purpose: string };
export type StructureTemplate = { id: string; name: string; kind?: string; beats: Beat[] };

// Preview shape — mirrors composition-service DecomposeResult (dataclasses.asdict).
// The chapter is nested under `chapter`; scenes carry resolved present_entity_ids
// PLUS the names the planner could not resolve against the roster.
export type PlannerScenePreview = {
  title: string;
  synopsis: string;
  tension: number;
  present_entity_ids: string[];
  present_entity_names_unresolved: string[];
  suggested_k: number;
};
export type PlannerChapterPreview = {
  chapter: { chapter_id: string; title: string; sort_order: number; beat_role: string | null; intent: string };
  scenes: PlannerScenePreview[];
  warning: string | null;
};
export type DecomposePreview = {
  arc_title: string;
  chapters: PlannerChapterPreview[];
  unmapped_beats: string[];
};

// Editable draft (what the UI mutates) + the commit payload (BE CommitRequest).
export type PlannerSceneDraft = { title: string; synopsis: string; tension: number | null; present_entity_ids: string[] };
export type PlannerChapterDraft = {
  chapter_id: string;
  title: string;
  intent: string;
  beat_role: string | null;
  scenes: PlannerSceneDraft[];
};
export type CommitDecomposePayload = {
  arc_title: string;
  chapters: PlannerChapterDraft[];
  replace: boolean;
  idempotency_key: string;
};

export type OutlineNode = {
  id: string;
  project_id: string;
  parent_id: string | null;
  kind: 'arc' | 'chapter' | 'scene' | 'beat';
  rank: string; // lexorank — the BE's primary within-parent order (story_order NULLS LAST, then rank)
  title: string;
  chapter_id: string | null;
  story_order: number | null;
  status: 'empty' | 'outline' | 'drafting' | 'done';
  synopsis: string;
  version: number;
  is_archived: boolean; // T1.1b — archived nodes are hidden unless the tree's "show archived" view is on
  beat_role: string | null; // T1.2 — the structure-template beat key this node fills (or null)
};

// T1.3 Scene Graph — a non-derivable scene edge (a causal/structural dependency
// the linear outline can't express). `setup_payoff` is the planted-payoff axis
// (solid arrow); `custom` is a free author-defined relation (dashed). Mirrors the
// BE SceneLink (app/db/models.py). Unique on (from,to,kind) → dup create 409s.
export type SceneLinkKind = 'setup_payoff' | 'custom';
export type SceneLink = {
  id: string;
  project_id: string;
  from_node_id: string;
  to_node_id: string;
  kind: SceneLinkKind;
  label: string;
};

// M9 chapter-gate (OI-1): can this chapter be published? can_publish is true
// only when every composition scene of the chapter is 'done' AND no scene's
// latest auto-generation left a CONFIRMED canon contradiction (A2-S3b / D4).
export type PublishGate = {
  chapter_id: string;
  scenes_total: number;
  scenes_done: number;
  // A2-S3b/A2-S4b — `canon_blocked` (an unresolved contradiction) is part of
  // can_publish (a HARD block); `canon_unchecked_scenes` is a NON-blocking
  // warning (dirty data — cast present but no resolved reading position).
  canon_blocked: boolean;
  canon_unresolved_scenes: number;
  canon_unchecked_scenes: number;
  can_publish: boolean;
};

export type Grounding = {
  blocks: Record<string, string>;
  prompt: string;
  profile: { source_language: string; voice: string; structure_pref: string };
  token_count: number;
  grounding_available: boolean;
  l4_dropped_no_position: number;
  warnings: string[];
};

export type CanonRule = {
  id: string;
  text: string;
  scope: 'world' | 'entity' | 'reveal_gate';
  entity_id: string | null;
  from_order: number | null;
  until_order: number | null;
  active: boolean;
  version: number;
};

export type Violation = {
  rule_id: string;
  violated: boolean;
  span: string;
  why: string;
  dismissed?: boolean;
};

export type Critic = {
  coherence: number | null;
  voice_match: number | null;
  pacing: number | null;
  canon_consistency: number | null;
  violations: Violation[];
  error?: string;
} | null;

export type GenerationJob = {
  id: string;
  project_id: string;
  outline_node_id: string | null;
  operation: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  result: { text?: string; measured?: boolean; output_tokens?: number } | null;
  critic: Critic;
};

// A2-S4 — the canon gate verdict on the converged auto winner (A2-S3b).
// `confirmed`: true → HARD (a confirmed contradiction survived auto-revision);
// null → ADVISORY (symbolic-only — the judge was down/not-distinct, unverified).
// The backend already EXCLUDES judge-cleared (confirmed=false) from `violations`;
// the FE filters defensively anyway.
export type CanonViolation = {
  kind: string;
  source: string; // "score_symbolic" | "llm_judge"
  entity_id: string;
  glossary_entity_id?: string | null;
  name?: string | null;
  status: string; // "gone"
  span?: string;
  matched?: string;
  confirmed?: boolean | null;
  why?: string;
};

// `status`: checked → canon was verified at the scene's reading position.
// skipped_no_cast / skipped_no_position / degraded → canon protection did NOT
// apply (dirty data / knowledge outage) — the FE warns "unchecked", never a
// false-green. `resolved` = no confirmed-HARD violation remains.
export type CanonResult = {
  violations: CanonViolation[];
  resolved: boolean;
  iterations: number;
  status: 'checked' | 'skipped_no_cast' | 'skipped_no_position' | 'degraded' | string;
};

// V1 slice 3 — controlled-auto (diverge→converge) result. NON-streaming: the
// auto /generate returns the winner + ALL K candidate texts so the FE shows
// every option as a card (the human gate).
export type AutoGeneration = {
  job_id: string;
  mode: 'auto';
  status: string;
  text: string; // the reranked winner
  winner_index: number;
  k: number;
  candidates: string[]; // the K drafts, winner included
  rerank_reason?: string;
  rerank_measured?: boolean;
  grounding_available?: boolean;
  reasoning_source?: string;
  reasoning_effort?: string | null;
  replay?: boolean;
  // A2-S4 — the canon gate verdict (absent on an idempotent replay / cowrite).
  canon?: CanonResult;
};

// LOOM chapter-assembly-modes — how a chapter's prose is assembled.
export type AssemblyMode = 'per_scene' | 'chapter';

// Response of the chapter single-pass (B2) + stitch (B3) endpoints. Non-stream
// JSON (like AutoGeneration) but chapter-scoped: no candidates (single pass).
export type ChapterGeneration = {
  job_id: string;
  status: string;
  text: string;
  canon?: CanonResult;
  assembly_mode: 'chapter' | 'per_scene_stitch';
  stitched?: boolean; // stitch arm: true = the LLM merge ran; false = raw concat
  degraded?: boolean; // stitch fell back to the raw concatenation
  persisted?: boolean; // best-effort write to the book draft (FE uses persist=false)
  draft_version?: number | null;
  persist_error?: string | null;
  reasoning_source?: string;
  reasoning_effort?: string | null;
  replay?: boolean;
};

// The genuine-author-choice actions on the gate (H2: NO 'accept' — accepting the
// winner as-is is not a correction). Maps 1:1 to the composition correction API.
export type CorrectionKind = 'edit' | 'pick_different' | 'regenerate' | 'reject';

// V1 slice 5 — the eval-gate dashboard. Per-mode correction rates (auto vs
// cowrite). Rates are null at cold-start (no generations of that mode).
export type ModeCorrectionStats = {
  mode: string;
  generations: number;
  corrected_jobs: number;
  accept_rate: number | null;
  edit_rate: number | null;
  pick_different_rate: number | null;
  regenerate_rate: number | null;
  reject_rate: number | null;
  avg_edit_magnitude: number | null;
};

export type CorrectionStats = {
  project_id: string;
  by_mode: ModeCorrectionStats[];
};

export type CorrectionBody = {
  kind: CorrectionKind;
  chosen_candidate_index?: number; // pick_different
  guidance?: string; // regenerate
  edited_text?: string; // edit
};

// One decoded SSE frame from POST /generate.
export type StreamEvent =
  | { type: 'job'; job_id: string; created: boolean; grounding_available: boolean; reasoning_source?: string; reasoning_effort?: string | null }
  | { type: 'token'; delta: string }
  | { type: 'reasoning'; delta: string }
  | { type: 'capped' }
  | { type: 'error'; error: string }
  | { type: 'done'; job_id: string; status: string; output_tokens?: number; measured?: boolean; capped?: boolean; replay?: boolean };

// T3.2 — selection-scoped AI operations on highlighted prose.
export type SelectionOperation = 'rewrite' | 'expand' | 'describe';
