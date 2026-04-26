/**
 * LLM client types — OpenAI-compatible chat completion API.
 * Compatible with: lmstudio, llama.cpp server, vLLM, OpenAI, Anthropic-via-proxy, etc.
 */

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatCompletionRequest {
  model: string;
  messages: ChatMessage[];
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
  /** Some providers accept response_format: { type: 'json_object' } */
  response_format?: { type: 'json_object' | 'text' };
}

export interface ChatCompletionResponse {
  id: string;
  object: string;
  created: number;
  model: string;
  choices: Array<{
    index: number;
    message: ChatMessage;
    finish_reason: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface LlmCallOptions {
  model: string;
  temperature?: number;
  maxTokens?: number;
  signal?: AbortSignal;
}

export interface LlmGenerationResult<T> {
  ok: boolean;
  /** Last attempt's parsed result (if any retry succeeded; undefined on full fail) */
  value?: T;
  /** Full attempt history for debugging */
  attempts: AttemptRecord[];
  /** Total LLM tokens used across all attempts */
  total_tokens?: number;
}

export interface AttemptRecord {
  attempt: number;
  prompt_messages_count: number;
  raw_response?: string;
  parse_error?: string;
  validation_errors?: string[];
  succeeded: boolean;
  duration_ms: number;
  tokens?: number;
}

export interface ValidationResult<T> {
  valid: boolean;
  value?: T;
  errors: string[];
}
