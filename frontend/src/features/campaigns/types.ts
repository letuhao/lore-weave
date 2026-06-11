// Auto-Draft Factory (S5c) — campaign types. Mirror the frozen campaign-service
// contracts (S1 + S4d budget + S5b/S5b-eval model matrix + S5a estimate).

export type CampaignStatus =
  | 'created' | 'running' | 'paused' | 'completed'
  | 'failed' | 'cancelling' | 'cancelled';

export interface Campaign {
  campaign_id: string;
  owner_user_id: string;
  book_id: string;
  name: string;
  status: CampaignStatus;
  gating_mode: string;
  stages: string[];
  target_language: string | null;
  knowledge_project_id: string | null;
  knowledge_model_source: string | null;
  knowledge_model_ref: string | null;
  translation_model_source: string | null;
  translation_model_ref: string | null;
  verifier_model_source: string | null;
  verifier_model_ref: string | null;
  eval_judge_model_source: string | null;
  eval_judge_model_ref: string | null;
  chapter_from: number | null;
  chapter_to: number | null;
  budget_usd: string | null;   // NUMERIC → string over the wire
  spent_usd: string;
  total_chapters: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  // #2 polish — present only on the list endpoint (translation done+skipped count
  // for the row's progress bar). Absent on get/detail.
  progress_done?: number;
}

export interface CampaignChapter {
  chapter_id: string;
  chapter_sort: number;
  ingest_status: string;
  knowledge_status: string;
  translation_status: string;
  eval_status: string;
  knowledge_attempts: number;
  translation_attempts: number;
  last_error: string | null;
  eval_fidelity_score: string | null;
}

export interface CampaignDetail extends Campaign {
  chapters: CampaignChapter[];
}

/** A per-role BYOK model pick (provider-registry user_model). */
export interface ModelPick {
  model_source: string | null;
  model_ref: string | null;
}

/** The six Model-Matrix roles. Embedding is BYOK user_model only (no source). */
export type ModelRole =
  | 'extractor' | 'translator' | 'verifier'
  | 'eval_judge' | 'embedding' | 'reranker';

export const MODEL_ROLES: ModelRole[] = [
  'extractor', 'translator', 'verifier', 'eval_judge', 'embedding', 'reranker',
];

/** The BYOK capability each role's picker filters by. */
export const ROLE_CAPABILITY: Record<ModelRole, string> = {
  extractor: 'chat',
  translator: 'chat',
  verifier: 'chat',
  eval_judge: 'chat',
  embedding: 'embedding',
  reranker: 'rerank',
};

/**
 * Does applying `embeddingPick` to `project` require the destructive confirm?
 * Mirrors knowledge-service's own guard: an embedding change is destructive only
 * when the project ALREADY has a graph (`extraction_status !== 'disabled'`) AND the
 * pick differs from the project's current model. A fresh project (disabled) sets the
 * model for free; an unset/identical pick is a no-op. The wizard shows the confirm
 * checkbox iff this is true, so the create's confirm_embedding_change matches what
 * the backend will 409 on. (Pure → unit-tested; see __tests__/embeddingConfirm.)
 */
export function needsEmbeddingConfirm(
  project: { embedding_model: string | null; extraction_status: string } | undefined,
  embeddingPick: string | null,
): boolean {
  if (!project || !embeddingPick) return false;
  return project.extraction_status !== 'disabled' && embeddingPick !== project.embedding_model;
}

export interface CreateCampaignPayload {
  book_id: string;
  name: string;
  gating_mode?: string;
  target_language?: string | null;
  knowledge_project_id: string;
  knowledge_model_source?: string | null;
  knowledge_model_ref?: string | null;
  translation_model_source?: string | null;
  translation_model_ref?: string | null;
  verifier_model_source?: string | null;
  verifier_model_ref?: string | null;
  eval_judge_model_source?: string | null;
  eval_judge_model_ref?: string | null;
  embedding_model_source?: string | null;
  embedding_model_ref?: string | null;
  rerank_model_source?: string | null;
  rerank_model_ref?: string | null;
  confirm_embedding_change?: boolean;
  chapter_from?: number | null;
  chapter_to?: number | null;
  budget_usd?: string | null;
  // G1 — launch-time estimate band (from /estimate), persisted for the report's
  // spent-vs-estimate. Omitted when launched without estimating.
  est_usd_low?: string | null;
  est_usd_high?: string | null;
}

export interface EstimateRequest {
  book_id: string;
  chapter_from?: number | null;
  chapter_to?: number | null;
  target_language?: string | null;
  models: Partial<Record<ModelRole, ModelPick>>;
}

export interface StageEstimate {
  stage: string;
  role: string;
  model_source: string | null;
  model_ref: string | null;
  status: string;          // ok | unpriced | not_found | bad_request | not_estimated
  estimated_usd: string;
}

export interface StageCounts {
  total: number;
  done: number;
  failed: number;
  skipped: number;
  in_progress: number;
}

/** D-S6-CHAPTER-PAGING — one server-side page of the per-chapter projection. */
export interface ChapterPage {
  items: CampaignChapter[];
  total: number;
}

/** S6 — lightweight live-progress payload (polled while a campaign is active). */
export interface CampaignProgress {
  campaign_id: string;
  status: CampaignStatus;
  spent_usd: string;
  budget_usd: string | null;
  total_chapters: number;
  stages: Record<'knowledge' | 'translation' | 'eval', StageCounts>;
}

/** G1 — failed chapters bucketed by normalized cause for the report. */
export interface ErrorGroup {
  cause: string;        // rate_limit | circuit_open | empty_body | zero_output | attempts_exhausted | other
  count: number;
  remediable: boolean;  // true → a re-run is likely to succeed
}

/** G1 — completion / wake-up report (terminal-campaign summary). */
export interface CampaignReport {
  campaign_id: string;
  status: CampaignStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  total_chapters: number;
  stages: Record<'knowledge' | 'translation' | 'eval', StageCounts>;
  spent_usd: string;
  budget_usd: string | null;
  est_usd_low: string | null;
  est_usd_high: string | null;
  error_groups: ErrorGroup[];
}

/** Statuses that are still progressing → the monitor keeps polling. */
export const ACTIVE_STATUSES: CampaignStatus[] = ['running', 'cancelling'];

export interface EstimateResponse {
  chapter_count: number;
  currency: string;
  estimated_usd_low: string;
  estimated_usd_high: string;
  estimated_minutes_low: number;
  estimated_minutes_high: number;
  per_stage: StageEstimate[];
  notes: string[];
  disclaimer: string;
}
