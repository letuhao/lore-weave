// K19a.2 — Discriminated union for the 13-state project-memory machine
// described in KNOWLEDGE_SERVICE_ARCHITECTURE.md §8.4.
//
// The FE derives one of these states from the backend `Project` row + any
// active ExtractionJob on every render in `useProjectState` (K19a.4). The
// ProjectStateCard component (K19a.3) dispatches to a per-state
// subcomponent based on `state.kind`.
//
// Naming convention in this file:
// - Shape fields that mirror a BE response verbatim (inside CostEstimate,
//   ExtractionJobSummary) stay snake_case. Any JSON-Decimal lands as a
//   string (matches existing Project.estimated_cost_usd in types.ts).
// - Discriminator payload fields that are UI-computed (oldModel,
//   budgetRemaining, canRetry, pendingCount) are camelCase per React
//   convention. They have no BE counterpart.
// - GraphStats is purely UI-derived — no BE endpoint returns this exact
//   shape. K19a.4 will compose it from multiple fetches.

// ── State kinds ──────────────────────────────────────────────────────────

export type ProjectStateKind =
  | 'disabled'
  | 'estimating'
  | 'ready_to_build'
  | 'building_running'
  | 'building_paused_user'
  | 'building_paused_budget'
  | 'building_paused_error'
  | 'complete'
  | 'stale'
  | 'failed'
  | 'model_change_pending'
  | 'cancelling'
  | 'deleting';

// ── Supporting types ─────────────────────────────────────────────────────

// JobScope mirrors BE `Literal["chapters","chat","glossary_sync","all"]`
// in services/knowledge-service/app/db/repositories/extraction_jobs.py.
// BE stores an optional chapter range in a separate `scope_range: dict`
// field; the UI flattens this into the `chapters` variant.
export type JobScope =
  | { kind: 'all' }
  | { kind: 'chapters'; range?: { from_sort: number; to_sort: number } }
  | { kind: 'chat' }
  | { kind: 'glossary_sync' };

// Mirrors EstimateResponse in services/knowledge-service/app/routers/public/extraction.py.
// Decimal fields arrive as strings (matches Project.estimated_cost_usd in
// types.ts).
export interface CostEstimate {
  items_total: number;
  items: {
    chapters: number;
    chat_turns: number;
    glossary_entities: number;
  };
  estimated_tokens: number;
  estimated_cost_usd_low: string;
  estimated_cost_usd_high: string;
  estimated_duration_seconds: number;
}

// Subset of BE ExtractionJob relevant to the state card. The full shape
// lives in services/knowledge-service/app/db/repositories/extraction_jobs.py.
// BE today reports single flat items_processed / items_total; the KSA
// §8.4b mockup shows per-source progress bars (glossary / chapters / chat)
// — that breakdown isn't in the BE response yet, so K19a.3 renders a
// single progress bar for now. When BE exposes per-source, add the field
// here rather than reshape in the UI.
export interface ExtractionJobSummary {
  job_id: string;
  status: ExtractionJobStatus;
  scope: JobScope;
  items_processed: number;
  items_total: number | null;
  cost_spent_usd: string;
  max_spend_usd: string | null;
  /** ISO-8601 UTC. */
  started_at: string;
  error_message: string | null;
}

// Mirrors BE JobStatus literal union.
export type ExtractionJobStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'complete'
  | 'failed'
  | 'cancelled';

// UI-derived; no BE endpoint returns this exact shape. K19a.4 composes
// it from multiple fetches (entity count, fact count, last_extracted_at
// from the Project row).
export interface GraphStats {
  entity_count: number;
  fact_count: number;
  event_count: number;
  passage_count: number;
  /** ISO-8601 UTC. */
  last_extracted_at: string;
}

// ── Discriminated union ──────────────────────────────────────────────────

export type ProjectMemoryState =
  | { kind: 'disabled' }
  | { kind: 'estimating'; scope: JobScope }
  | { kind: 'ready_to_build'; estimate: CostEstimate }
  | { kind: 'building_running'; job: ExtractionJobSummary }
  | { kind: 'building_paused_user'; job: ExtractionJobSummary }
  | { kind: 'building_paused_budget'; job: ExtractionJobSummary; budgetRemaining: number }
  | { kind: 'building_paused_error'; job: ExtractionJobSummary; error: string }
  | { kind: 'complete'; stats: GraphStats }
  | { kind: 'stale'; stats: GraphStats; pendingCount: number }
  | { kind: 'failed'; error: string; canRetry: boolean }
  | { kind: 'model_change_pending'; oldModel: string; newModel: string }
  | { kind: 'cancelling' }
  | { kind: 'deleting' };

// ── Transitions ──────────────────────────────────────────────────────────

// Authoritative source: KNOWLEDGE_SERVICE_ARCHITECTURE.md §8.4. Do NOT
// add edges here without updating the diagram there first — UI drift
// from the designed state machine breaks button visibility invariants.
//
// Intermediate hops in the KSA diagram (e.g. "Pause → cancelling →
// building_paused_user") are encoded as two edges so `canTransition`
// stays a simple table lookup. Progress ticks on building_running are
// NOT a transition (same-state updates); they are not edges here.
//
// Used by K19a.3 action-button visibility, NOT by K19a.4 state derivation
// — K19a.4 computes state from BE fields, not from prior state.
export const VALID_TRANSITIONS: Record<ProjectStateKind, readonly ProjectStateKind[]> = {
  disabled: ['estimating', 'building_running'],
  estimating: ['ready_to_build', 'disabled'],
  ready_to_build: ['building_running', 'disabled'],
  building_running: [
    'complete',
    'cancelling',
    'building_paused_budget',
    'building_paused_error',
    'failed',
  ],
  building_paused_user: ['building_running', 'disabled'],
  building_paused_budget: ['building_running', 'disabled', 'ready_to_build'],
  building_paused_error: ['building_running', 'disabled', 'failed'],
  complete: ['stale', 'building_running', 'deleting', 'model_change_pending'],
  stale: ['building_running', 'complete'],
  failed: ['estimating', 'deleting'],
  model_change_pending: ['deleting', 'complete'],
  cancelling: ['building_paused_user', 'disabled'],
  deleting: ['disabled'],
};

export function canTransition(from: ProjectStateKind, to: ProjectStateKind): boolean {
  return VALID_TRANSITIONS[from].includes(to);
}
