// LOOM Composition (M8) — FE types mirroring the composition-service contract.

export type Work = {
  project_id: string;
  user_id: string;
  book_id: string;
  active_template_id: string | null;
  status: 'active' | 'archived';
  settings: Record<string, unknown>;
  version: number;
};

export type WorkResolution = {
  status: 'found' | 'candidates' | 'unmarked_single' | 'unmarked_candidates' | 'none' | 'unavailable';
  work: Work | null;
  candidates: Work[];
  book_project_id: string | null;
  book_project_ids: string[];
};

export type OutlineNode = {
  id: string;
  project_id: string;
  parent_id: string | null;
  kind: 'arc' | 'chapter' | 'scene' | 'beat';
  title: string;
  chapter_id: string | null;
  story_order: number | null;
  status: 'empty' | 'outline' | 'drafting' | 'done';
  synopsis: string;
  version: number;
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
