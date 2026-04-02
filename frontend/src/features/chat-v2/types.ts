// ── Chat V2 Types ─────────────────────────────────────────────────────────────
// Mirrors chat-service backend models.

export interface ChatSession {
  session_id: string;
  owner_user_id: string;
  title: string;
  model_source: string;
  model_ref: string;
  system_prompt: string | null;
  status: 'active' | 'archived';
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  owner_user_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  content_parts: unknown | null;
  sequence_num: number;
  input_tokens: number | null;
  output_tokens: number | null;
  model_ref: string | null;
  is_error: boolean;
  error_detail: string | null;
  parent_message_id: string | null;
  created_at: string;
}

export interface ChatOutput {
  output_id: string;
  message_id: string;
  session_id: string;
  owner_user_id: string;
  output_type: 'text' | 'code' | 'image' | 'audio' | 'video' | 'file';
  title: string | null;
  content_text: string | null;
  language: string | null;
  storage_key: string | null;
  mime_type: string | null;
  file_name: string | null;
  file_size_bytes: number | null;
  metadata: unknown | null;
  created_at: string;
}

export interface CreateSessionPayload {
  model_source: string;
  model_ref: string;
  title?: string;
  system_prompt?: string;
}

export interface PatchSessionPayload {
  title?: string;
  system_prompt?: string;
  model_source?: string;
  model_ref?: string;
  status?: string;
}
