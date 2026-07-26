// ── Extraction Profile (from GET /v1/glossary/books/{bookId}/extraction-profile) ──

export type ExtractionProfileAttribute = {
  code: string;
  name: string;
  field_type: string;
  description: string | null;
  auto_fill_prompt: string | null;
  is_required: boolean;
  auto_selected: boolean;
};

export type ExtractionProfileKind = {
  kind_id: string;
  code: string;
  name: string;
  icon: string;
  auto_selected: boolean;
  attributes: ExtractionProfileAttribute[];
};

export type ExtractionProfileResponse = {
  kinds: ExtractionProfileKind[];
};

// ── Extraction Job Request (POST /v1/extraction/books/{bookId}/extract-glossary) ──

/**
 * Per-attribute merge action.
 * - `default` — defer to the attribute's authored merge_strategy (the accumulate-by-default
 *   path: tags→append, state→overwrite, identity→fill). This is what auto-selected attrs use
 *   so re-extraction advances knowledge instead of freezing (D-EXTRACT-ATTR-MERGE-DEFAULTS).
 * - `fill` — write only if empty (write-once).
 * - `append` — accumulate into a multi-value attribute (deduped).
 * - `overwrite` — replace the existing value (last-write-wins, audit-logged).
 * - `skip` — do not extract this attribute.
 */
export type AttributeAction = 'default' | 'fill' | 'append' | 'overwrite' | 'skip';

/** kind_code → { attr_code → action } */
export type ExtractionProfile = Record<string, Record<string, AttributeAction>>;

export type ContextFilters = {
  alive?: boolean;
  min_frequency?: number;
  recency_window?: number;
  limit?: number;
};

export type ExtractionJobRequest = {
  chapter_ids: string[];
  extraction_profile: ExtractionProfile;
  model_source: string;
  model_ref: string;
  max_entities_per_kind?: number;
  context_filters?: ContextFilters;
  /** Reasoning effort (off|low|medium|high|auto) for the extraction LLM. Default
   *  'off' — extraction is structured JSON where thinking mostly wastes budget. The
   *  BE (translation-service extraction router) accepts this; `thinking_enabled` is
   *  its deprecated bool alias (True→medium). */
  reasoning_effort?: string;
  thinking_enabled?: boolean;
  /** Parallel LLM calls per chapter (the window×batch fan-out). Omitted/1 ⇒ sequential.
   *  The worker clamps to a hard ceiling (16). */
  concurrency_level?: number;
};

// ── Extraction Job Response (from POST 202 + GET /v1/extraction/jobs/{jobId}) ──

export type CostEstimate = {
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_total_tokens: number;
  llm_calls: number;
  chapters_count: number;
  batches_per_chapter: number;
};

export type ExtractionJobCreated = {
  job_id: string;
  status: string;
  job_type: string;
  total_chapters: number;
  cost_estimate: CostEstimate;
};

export type ExtractionChapterResult = {
  chapter_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  entities_found: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  error_message: string | null;
};

export type ExtractionJobStatus = {
  job_id: string;
  book_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'cancelling' | 'completed_with_errors';
  job_type: string;
  source_language: string;
  total_chapters: number;
  completed_chapters: number;
  failed_chapters: number;
  entities_created: number;
  entities_updated: number;
  entities_skipped: number;
  total_input_tokens: number;
  total_output_tokens: number;
  cost_estimate: CostEstimate | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  chapters: ExtractionChapterResult[];
};

export type CancelJobResponse = {
  job_id: string;
  status: string;
};
