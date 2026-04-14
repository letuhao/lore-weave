// ── Chat V2 Types ─────────────────────────────────────────────────────────────
// Mirrors chat-service backend models.

export interface GenerationParams {
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  thinking?: boolean | null;
}

export interface ChatSession {
  session_id: string;
  owner_user_id: string;
  title: string;
  model_source: string;
  model_ref: string;
  system_prompt: string | null;
  generation_params: GenerationParams;
  is_pinned: boolean;
  status: 'active' | 'archived';
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  // K8.4: set when the session is linked to a knowledge-service
  // project. Drives the memory-mode indicator in ChatHeader —
  // null means Mode 1 (global bio only), non-null means Mode 2
  // (static project memory). Mirrors the backend column added
  // by chat-service's K5 migration.
  project_id: string | null;
  // K-CLEAN-5 (D-K8-04): memory mode for the chat header
  // MemoryIndicator.
  //   no_project — no project linked, AI sees only the global bio
  //   static     — project linked, AI sees its summary + glossary
  //   degraded   — knowledge-service was unreachable on the last
  //                turn and chat-service fell back to recent-only
  // GET responses populate from `project_id` (no_project | static).
  // The SSE stream emits a `memory-mode` event on every turn so the
  // FE can flip to `degraded` when the upstream call falls back.
  memory_mode?: 'no_project' | 'static' | 'degraded';
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  owner_user_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  content_parts: unknown | null;
  sequence_num: number;
  branch_id: number;
  input_tokens: number | null;
  output_tokens: number | null;
  model_ref: string | null;
  is_error: boolean;
  error_detail: string | null;
  parent_message_id: string | null;
  created_at: string;
}

export interface BranchInfo {
  branch_id: number;
  message_count: number;
  created_at: string | null;
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
  generation_params?: GenerationParams;
}

export interface PatchSessionPayload {
  title?: string;
  system_prompt?: string;
  model_source?: string;
  model_ref?: string;
  status?: string;
  generation_params?: GenerationParams;
  is_pinned?: boolean;
  // K9.1: link the session to a knowledge-service project (or clear
  // it with explicit null). Backend chat-service uses model_fields_set
  // to distinguish "not provided" from "set to null", so JSON.stringify
  // must emit `"project_id": null` for the clear case — keep this
  // explicitly nullable rather than `string | undefined`.
  project_id?: string | null;
}
