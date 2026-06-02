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
}

export interface AutoEnrichResponse {
  project_id: string;
  job_id?: string;
  entities_scanned: number;
  detected: number;
  enqueued_gaps?: number;
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
  provenance_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
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
