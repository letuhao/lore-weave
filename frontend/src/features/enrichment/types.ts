// Types for the lore-enrichment review feature.
// Mirrors services/lore-enrichment-service `enrichment_proposal` as_dict + the
// gaps / sources / jobs response shapes. Gateway prefix: /v1/lore-enrichment.
//
// H0 (enriched != canon): a proposal ALWAYS has origin='enrichment', confidence<1.0,
// and review_status starts at 'proposed'. Promotion to canon is the explicit,
// author-only act (the ④ copyright-safety gate).

export type ReviewStatus =
  | 'proposed'
  | 'author_reviewing'
  | 'approved'
  | 'promoted'
  | 'rejected';

export type Technique = 'template' | 'retrieval' | 'fabrication' | 'recook';

/** P-tier of a technique (P1 template/retrieval · P2 fabrication · P3 recook). */
export type Tier = 'P1' | 'P2' | 'P3';

export type VerifyStatus =
  | 'verified_clean'
  | 'needs_review'
  | 'quarantined'
  | 'degraded'
  | 'auto_rejected';

export type VerifyFlagKind =
  | 'contradiction'
  | 'anachronism'
  | 'injection'
  | 'regurgitation';

export type Severity = 'low' | 'medium' | 'high';

export interface VerifyFlag {
  kind: VerifyFlagKind | string;
  dimension: string | null;
  evidence: string;
  severity: Severity | string;
}

/** provenance_json.canon_verify — the C12 + ③ verify annotation (never canon). */
export interface CanonVerify {
  passed: boolean;
  verify_degraded: boolean;
  flags: VerifyFlag[];
}

/** A source the recook (②) skipped because it was not admissible (default-deny). */
export interface SkippedSource {
  corpus_id?: string;
  name?: string;
  license?: string;
  reason?: string;
  [k: string]: unknown;
}

/** provenance_json: technique + the generated dimension map + the verify annotation
 *  (+ recook extras). Annotation only — never a canon marker (H0). */
export interface Provenance {
  technique?: string;
  dimensions?: Record<string, string>;
  canon_verify?: CanonVerify;
  verify_status?: VerifyStatus | string;
  skipped_unlicensed_sources?: SkippedSource[];
  /** Per-strategy grounding meta — the generation `model_ref` (a user_model_id)
   *  lives here for retrieval/fabrication; recook mirrors it under `recook`. */
  retrieval?: { model_ref?: string; top_k?: number; grounding_count?: number };
  recook?: { model_ref?: string; [k: string]: unknown };
  [k: string]: unknown;
}

/** One grounding/source reference the proposal cites (source_refs_json). The exact
 *  shape is strategy-dependent, so it is rendered defensively. */
export interface SourceRef {
  corpus_id?: string;
  grounding_ref_id?: string;
  locator?: string;
  excerpt?: string;
  license?: string;
  score?: number;
  [k: string]: unknown;
}

export interface Proposal {
  proposal_id: string;
  job_id: string;
  project_id: string;
  user_id: string;
  entity_kind: string;
  target_ref: string | null;
  canonical_name: string | null;
  content: string;
  origin: string; // always 'enrichment' (H0)
  technique: Technique | string;
  provenance_json: Provenance;
  confidence: number; // always < 1.0 (H0)
  source_refs_json: SourceRef[];
  cultural_grounding_ref_id: string | null;
  review_status: ReviewStatus;
  writeback_entity_id: string | null;
  promoted_entity_id: string | null;
  promoted_by: string | null;
  promoted_at: string | null;
  promoted_from_proposal_id: string | null;
  original_technique: string | null;
  rejected_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProposalListResponse {
  items: Proposal[];
  total: number;
  limit: number;
  offset: number;
}

export interface PromoteResult {
  proposal_id: string;
  review_status: ReviewStatus;
  promoted_entity_id: string | null;
  promoted_by: string | null;
  promoted_at: string | null;
  origin: string;
  facts_promoted?: number;
  canon?: unknown;
}

// ── Gaps ────────────────────────────────────────────────────────────────────
export interface Gap {
  rank: number;
  score: number;
  canonical_name: string;
  entity_kind: string;
  mention_count: number;
  present_dimensions: string[];
  missing_dimensions: string[];
}

export interface DetectGapsResponse {
  project_id: string;
  book_id: string;
  entities_scanned: number;
  gap_count: number;
  gaps: Gap[];
  /** C2 "extract first" signal — true when the book has NO extracted entities yet
   *  (enrichment is downstream of extraction; there is nothing to enrich). */
  needs_extraction?: boolean;
  message?: string;
}

/** A specific gap to enrich (LE-064 per-row "enrich →"). The backend re-derives
 *  the missing dimensions, so only the anchor + present dimensions are needed. */
export interface EnrichTarget {
  canonical_name: string;
  target_ref?: string;
  entity_kind: string;
  mention_count?: number;
  present_dimensions?: string[];
}

/** Build an EnrichTarget from a detected Gap (for the per-row enrich action). */
export function gapToTarget(g: Gap): EnrichTarget {
  return {
    canonical_name: g.canonical_name,
    target_ref: g.canonical_name,
    entity_kind: g.entity_kind,
    mention_count: g.mention_count,
    present_dimensions: g.present_dimensions,
  };
}

export interface AutoEnrichResponse {
  project_id: string;
  job_id?: string;
  entities_scanned: number;
  detected: number;
  enqueued_gaps?: number;
  enqueued?: boolean;
}

// ── Compose (unified input modes — slice 1: gap | draft) ───────────────────────
/** The input source a compose run starts from. Slice 1 ships gap | draft;
 *  context | files | intent land in slices 2–4 (the backend 400s them for now). */
export type ComposeInputSource = 'gap' | 'draft' | 'context' | 'files' | 'intent';

/** Mode D expand strategy — keep the draft verbatim and only add missing dims
 *  (add_only) or rewrite + voice-sync it preserving meaning (rewrite). */
export type ExpandMode = 'add_only' | 'rewrite';

/** Mode C license assertion (contract enum). `copyrighted` is default-denied by the
 *  backend (403); `owned` is stored as `licensed` (re-cook-admissible). */
export type ContextLicense = 'public_domain' | 'licensed' | 'owned' | 'copyrighted';

/** The entity a compose run targets — an existing glossary entity OR a new one.
 *  For mode='new' the backend mints the glossary anchor only at PROMOTE (H0-clean);
 *  here `target_ref` stays null. */
export interface ComposeTargetInput {
  mode: 'existing' | 'new';
  canonical_name: string;
  entity_kind: string;
  target_ref?: string | null;
  present_dimensions?: string[];
  /** Dimension picker (#1): the exact dimensions to enrich (ids/labels). undefined =
   *  auto (server derives from coverage / enriches all); when set, exactly these. */
  requested_dimensions?: string[] | null;
}

/** One choosable dimension for a kind (GET .../dimensions) — the picker's chips. */
export interface ComposeDimension {
  id: string;
  label: string;
  required: boolean;
}

/** The POST /compose body (the api layer adds book_id := bookId). */
export interface ComposeBody {
  input_source: ComposeInputSource;
  /** Required for `gap`; OPTIONAL for `draft` (mode D does no retrieval/embed). */
  embedding_model_ref?: string;
  generation_model_ref: string;
  target?: ComposeTargetInput;
  draft_text?: string;
  expand_mode?: ExpandMode;
  /** Mode C (context): pasted reference text + the author's license assertion. */
  context_text?: string;
  context_license?: ContextLicense;
  /** Mode F (files): uploaded file ids (from POST /uploads) to ingest as grounding. */
  upload_ids?: string[];
  /** Mode B (intent): the original free-text intent (audit; the run uses `target`). */
  intent_text?: string;
  gap_targets?: ComposeTargetInput[];
  technique?: string;
  max_spend_usd?: number | null;
  top_k?: number;
}

/** Mode F upload lifecycle (async extract+OCR; poll until ready/failed). */
export type UploadStatus = 'processing' | 'ready' | 'failed';
export interface UploadResult {
  upload_id: string;
  filename: string;
  mime?: string;
  pages?: number;
  extracted_chars?: number;
  ocr_used?: boolean;
  license_asserted?: string;
  status: UploadStatus;
  error?: string | null;
}

/** Mode B (intent) — the resolver's proposal (step 1; no job yet). */
export interface ResolvedIntent {
  target: { mode: 'existing' | 'new'; canonical_name: string; entity_kind: string };
  dimensions: string[];
  technique: string;
  rationale: string;
}

/** POST /compose result — async 202 + job_id. */
export interface ComposeResult {
  project_id: string;
  job_id?: string;
  input_source: string;
  technique: string;
  enqueued_targets?: number;
  enqueued?: boolean;
}

// ── Sources (corpus) ──────────────────────────────────────────────────────────
export type SourceKind = 'fengshen' | 'shanhaijing' | 'history' | 'other';

export type License =
  | 'public_domain'
  | 'public-domain'
  | 'licensed'
  | 'unlicensed'
  | 'copyrighted'
  | 'restricted'
  | 'unknown';

export interface Source {
  corpus_id: string;
  project_id: string;
  name: string;
  kind: SourceKind | string;
  license: License | string;
  /** # of ingested+embedded chunks (GET /sources echoes it; absent before ingest). */
  chunk_count?: number;
  provenance_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** POST /sources/{id}/ingest result — chunk+embed counts. */
export interface IngestResult {
  corpus_id: string;
  chunks_total: number;
  chunks_inserted: number;
  chunks_embedded: number;
}

/** POST /books/{id}/ground result — author-selected chapters → grounding corpus (C2). */
export interface GroundResult {
  book_id: string;
  chapters_ingested: number;
  chunks_total: number;
  chunks_inserted: number;
  chunks_embedded: number;
}

export interface SourceListResponse {
  items: Source[];
  total: number;
  limit: number;
  offset: number;
}

// ── Jobs ──────────────────────────────────────────────────────────────────────
export type JobStatus =
  | 'pending'
  | 'estimating'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface Job {
  job_id: string;
  project_id: string;
  status: JobStatus | string;
  technique: string;
  entity_kind: string | null;
  book_id: string | null;
  proposals_total: number;
  estimated_cost: number;
  actual_cost: number;
  max_spend: number | null;
  error_message: string | null;
  created_at: string;
}

export interface JobListResponse {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
}

// ── Book profile (de-bias C3) ───────────────────────────────────────────────────
/** The built-in entity kinds with a static dimension table (others → GENERIC).
 *  The dimension-override editor keys on these. */
export const PROFILE_KINDS = ['character', 'location', 'item', 'faction', 'event'] as const;
export type ProfileKind = (typeof PROFILE_KINDS)[number];

/** The entity-kinds a compose target may use: the C1 modeled kinds + `generic`
 *  (the freeform fallback). Drives the new-entity kind dropdown (Compose slice 1). */
export const COMPOSE_KINDS = [...PROFILE_KINDS, 'generic'] as const;
export type ComposeKind = (typeof COMPOSE_KINDS)[number];

/** One author/AI-added dimension within a kind's `add` list. */
export interface DimensionAdd {
  id: string;
  label?: string;
  weight?: number;
  required?: boolean;
  payload_shape?: string;
}

/** Per-kind override ops (the dynamic-dimension layer). The FE editor edits `add`;
 *  `remove`/`relabel`/`reweight` are preserved untouched (round-trip safe). */
export interface DimensionOverrideOps {
  add?: DimensionAdd[];
  remove?: string[];
  relabel?: Record<string, string>;
  reweight?: Record<string, number>;
}

export type DimensionOverrides = Record<string, DimensionOverrideOps>;

export interface AnachronismMarker {
  term: string;
  reason: string;
}

/** GET/PUT /books/{id}/profile — the persisted de-bias profile. */
export interface BookProfile {
  book_id: string | null;
  worldview: string;
  language: string;
  era_policy: string | null;
  voice: string | null;
  anachronism_markers: AnachronismMarker[];
  anachronism_enabled: boolean;
  dimension_overrides: DimensionOverrides;
  profile_source: 'seed' | 'ai_suggested' | 'manual';
}

/** PUT body — the full profile to persist (FULL REPLACE: omitted fields reset). */
export interface BookProfileInput {
  worldview: string;
  language: string;
  era_policy: string | null;
  voice: string | null;
  anachronism_markers: AnachronismMarker[];
  dimension_overrides: DimensionOverrides;
}

/** POST /books/{id}/profile/suggest — a non-persisted AI draft. */
export interface SuggestedProfile {
  worldview: string;
  language: string;
  era_policy: string | null;
  voice: string | null;
  dimension_overrides: DimensionOverrides;
  profile_source: 'ai_suggested';
}

// ── helpers ────────────────────────────────────────────────────────────────────
export function tierOf(technique: string): Tier {
  if (technique === 'fabrication') return 'P2';
  if (technique === 'recook') return 'P3';
  return 'P1';
}

/** The default-deny admissible licenses for recook (everything else is refused). */
export function isRecookable(license: string): boolean {
  return (
    license === 'public_domain' ||
    license === 'public-domain' ||
    license === 'licensed'
  );
}
