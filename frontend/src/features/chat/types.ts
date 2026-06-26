// ── Chat V2 Types ─────────────────────────────────────────────────────────────
// Mirrors chat-service backend models.

export type ReasoningEffort = 'off' | 'auto' | 'low' | 'medium' | 'high';

export interface GenerationParams {
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  thinking?: boolean | null;
  // Granular reasoning effort (takes precedence over `thinking`). 'off' disables hidden
  // thinking — the fix for an over-thinking model that loops without finishing.
  reasoning_effort?: ReasoningEffort | null;
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
  // A2A phase-2: optional "composer" model. When set, the orchestrator
  // (model_ref) can call compose_prose, which streams THIS model for prose.
  composer_model_source?: string | null;
  composer_model_ref?: string | null;
  // D-PLAN-PLANNER-DEFAULT-FE phase 2: optional per-session planner model.
  planner_model_source?: string | null;
  planner_model_ref?: string | null;
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

// MCP fan-out (C-ACTIVITY) — one auto-applied (Tier-A) op the agent ran this
// turn. Streamed as an AG-UI CUSTOM event (`name:"activity"`, value = this
// shape) and rendered as an Undo strip in the chat. `undo.available=false`
// when the op has no reverse; Undo issues the named reverse tool via a fresh
// turn. See the fan-out plan §3 C-ACTIVITY.
export interface ActivityUndo {
  available: boolean;
  /** reverse tool name to call on Undo (e.g. "chapter_delete") */
  tool?: string;
  /** args for the reverse tool */
  args?: Record<string, unknown>;
}

export interface ActivityEvent {
  /** dotted op id, e.g. "chapter.create" */
  op: string;
  /** human summary, e.g. "Created draft chapter 'Chapter 5'" */
  summary: string;
  undo?: ActivityUndo;
}

// K21-C (D1/D2): one tool invocation recorded during an assistant turn.
// Surfaced both live (accumulated from the `tool-call` SSE event in
// useChatMessages) and on replay (the `tool_calls` JSONB column the
// chat-service read API now returns). `tool` + `ok` are always present;
// the optional fields are populated when the executor includes them.
export interface ToolCallRecord {
  tool: string;
  ok: boolean;
  iteration?: number;
  args?: unknown;
  result?: unknown;
  error?: string | null;
  // ARCH-1 C6 — frontend tool (propose_edit) awaiting the user's apply/dismiss.
  // When `pending`, the chip renders Apply/Dismiss; runId/toolCallId resume the
  // suspended run via the tool-results endpoint.
  pending?: boolean;
  runId?: string;
  toolCallId?: string;
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
  // K21-C (D1): tool calls the assistant made during this turn.
  // null/absent for user messages and pre-K21 assistant messages.
  tool_calls?: ToolCallRecord[] | null;
  // MCP fan-out (C-ACTIVITY): Tier-A auto-applied ops streamed this turn,
  // rendered as an Undo strip. null/absent when the turn auto-applied nothing.
  activities?: ActivityEvent[] | null;
}

export interface BranchInfo {
  branch_id: number;
  message_count: number;
  created_at: string | null;
}

// K21-C (D5/D8): a fact the assistant's `memory_remember` tool queued
// for the user to confirm/reject — only created when the project has
// `memory_remember_confirm` on. Mirrors knowledge-service
// app/db/models.py PendingFact. `fact_text` is already injection-
// neutralized server-side (design D6).
export type PendingFactType = 'decision' | 'preference' | 'milestone' | 'negation';

export interface PendingFact {
  pending_fact_id: string;
  user_id: string;
  project_id: string | null;
  session_id: string;
  fact_type: PendingFactType;
  fact_text: string;
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
  // A2A phase-2: set/clear the composer model. Same model_fields_set
  // semantics as project_id — emit explicit null to clear.
  composer_model_source?: string | null;
  composer_model_ref?: string | null;
  // D-PLAN-PLANNER-DEFAULT-FE phase 2: set/clear the per-session planner model.
  planner_model_source?: string | null;
  planner_model_ref?: string | null;
}
