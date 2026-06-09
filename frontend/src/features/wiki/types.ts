export interface WikiKindSummary {
  kind_id: string;
  code: string;
  name: string;
  icon: string;
  color: string;
}

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
