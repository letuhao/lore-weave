export type OverwriteMode = 'missing_only' | 'refresh_machine';

export type GlossaryTranslateCostEstimate = {
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_total_tokens: number;
  llm_calls: number;
  entity_count: number;
  attr_count: number;
};

export type GlossaryTranslateJobRequest = {
  target_language: string;
  model_source: string;
  model_ref: string;
  overwrite_mode: OverwriteMode;
  /** Enable model reasoning/thinking (LM Studio enable_thinking). */
  thinking_enabled?: boolean;
  /** bug #4: how many entities translate in parallel (1 = sequential). Omitted ⇒ 1. */
  concurrency_level?: number;
};

export type GlossaryTranslateJobCreated = {
  job_id: string;
  status: string;
  job_type: string;
  total_entities: number;
  cost_estimate: GlossaryTranslateCostEstimate;
};

export type GlossaryTranslateJobStatus = {
  job_id: string;
  book_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'cancelling' | 'completed_with_errors';
  job_type: string;
  source_language: string;
  target_language: string;
  overwrite_mode: OverwriteMode;
  total_entities: number;
  completed_entities: number;
  failed_entities: number;
  attrs_translated: number;
  attrs_skipped: number;
  total_input_tokens: number;
  total_output_tokens: number;
  cost_estimate: GlossaryTranslateCostEstimate | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type CancelJobResponse = {
  job_id: string;
  status: string;
};
