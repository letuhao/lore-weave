export interface WikiKindSummary {
  kind_id: string;
  code: string;
  name: string;
  icon: string;
  color: string;
}

/** wiki-llm M7b — AI-generation status: null (human-authored) | 'generated'
 *  (clean) | 'needs_review' (verify flags) | 'blocked' (publish-blocked). */
export type WikiGenerationStatus = 'generated' | 'needs_review' | 'blocked';

export interface WikiArticleListItem {
  article_id: string;
  entity_id: string;
  book_id: string;
  display_name: string;
  kind: WikiKindSummary;
  status: string;
  template_code: string | null;
  revision_count: number;
  updated_at: string;
  generation_status?: WikiGenerationStatus | null;
  /** wiki-llm Phase-2 — a knowledge source changed; show an "Outdated" badge. */
  is_knowledge_stale?: boolean;
}

export interface WikiArticleListResp {
  items: WikiArticleListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface WikiAttrTranslation {
  translation_id: string;
  attr_value_id: string;
  language_code: string;
  value: string;
  confidence: string;
  translator?: string;
  updated_at: string;
}

export interface WikiAttrDef {
  attr_def_id: string;
  code: string;
  name: string;
  field_type: string;
  is_required: boolean;
  is_system: boolean;
  sort_order: number;
}

export interface WikiInfoboxAttr {
  attr_value_id: string;
  entity_id: string;
  attr_def_id: string;
  attribute_def: WikiAttrDef;
  original_language: string;
  original_value: string;
  translations: WikiAttrTranslation[];
  evidences: unknown[];
}

/** One serialized CanonVerifier flag, from generation_provenance.verify_flags. */
export interface WikiVerifyFlag {
  kind: string;
  dimension: string;
  evidence: string;
  severity: string;
}

/** generation_provenance JSON written by M5 (the subset the FE reads). */
export interface WikiGenerationProvenance {
  verify_flags?: WikiVerifyFlag[];
  publish_blocked?: boolean;
  model_ref?: string;
  citations?: unknown[];
  prompt_version?: string;
  pipeline_version?: string;
  [k: string]: unknown;
}

export interface WikiArticleDetail {
  article_id: string;
  entity_id: string;
  book_id: string;
  display_name: string;
  kind: WikiKindSummary;
  status: string;
  template_code: string | null;
  revision_count: number;
  updated_at: string;
  body_json: Record<string, unknown>;
  spoiler_chapters: string[];
  infobox: WikiInfoboxAttr[];
  created_at: string;
  generation_status?: WikiGenerationStatus | null;
  generation_provenance?: WikiGenerationProvenance | null;
  generated_at?: string | null;
  is_knowledge_stale?: boolean;
}

export interface WikiRevisionListItem {
  revision_id: string;
  article_id: string;
  version: number;
  author_id: string;
  author_type: string;
  summary: string;
  created_at: string;
}

export interface WikiRevisionListResp {
  items: WikiRevisionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface WikiRevisionDetail extends WikiRevisionListItem {
  body_json: Record<string, unknown>;
}

export interface WikiSuggestionResp {
  suggestion_id: string;
  article_id: string;
  user_id: string;
  diff_json: Record<string, unknown>;
  reason: string;
  status: string;
  reviewer_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  article_display_name?: string;
}

export interface WikiSuggestionListResp {
  items: WikiSuggestionResp[];
  total: number;
  limit: number;
  offset: number;
}

/* ── wiki-llm Phase-2 — change-control / "Knowledge updates" ──────────────── */

/** One pending staleness entry in the change-feed (§5.3). */
export interface WikiStalenessRow {
  staleness_id: string;
  article_id: string;
  entity_id: string;
  display_name: string;
  kind: WikiKindSummary;
  reason_code: string;
  severity: 'hard' | 'structural' | 'content' | (string & {});
  source_ref: Record<string, unknown>;
  generation_status?: WikiGenerationStatus | null;
  detected_at: string;
}

export interface WikiStalenessListResp {
  items: WikiStalenessRow[];
  total: number;
}

/* ── wiki-llm M7b — LLM generation jobs ──────────────────────────────────── */

export type WikiGenJobState =
  | 'pending'
  | 'running'
  | 'paused'
  | 'complete'
  | 'failed'
  | 'cancelled';

/** Poll shape from GET /v1/glossary/books/{id}/wiki/job (knowledge via proxy). */
export interface WikiGenJobStatus {
  job_id: string;
  status: WikiGenJobState;
  model_source: string;
  model_ref: string;
  items_total: number | null;
  items_processed: number;
  items_done_count: number;
  entity_count: number;
  cost_spent_usd: string | number;
  max_spend_usd: string | number | null;
  error_message: string | null;
}

/** Flat per-article wiki-gen cost (D-WIKI-P2B-COST-ESTIMATE). Decimal serializes
 *  as a string over JSON. */
export interface WikiGenConfig {
  cost_per_article_usd: string | number;
}

/**
 * The generate endpoint is overloaded: with no model it renders deterministic
 * stubs ({created}); with a model it DELEGATES to the LLM batch generator, which
 * returns a job ({job_id,status}, 202) or {action:'none'} when no entity matched.
 * A 409 (active job already running) is thrown by apiJson — caught in the hook.
 */
export type WikiGenerateResult =
  | { created: number; articles: unknown[] }
  | { job_id: string; status: string }
  | { action: 'none'; entities: number };
