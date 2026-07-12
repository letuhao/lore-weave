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
  // D-COMPOSE-SESSION-RESTORE: set when the session was created from a
  // book-scoped host (the Writing Studio Compose panel). Independent of
  // project_id — a book with no knowledge project yet still gets a durable
  // book_id so its session (and chosen model) can be found again on reopen.
  book_id?: string | null;
  // T-4 / WS-1.10: the session discriminator — 'assistant' for a Work Assistant session,
  // 'chat' (default) for everything else. Recall + work-capture gate on it.
  session_kind?: 'chat' | 'assistant';
  // WS-1.6: the last persisted per-turn capture decision ({fire, reason}) so the assistant
  // home strip can render capture visibly ON/OFF with a reason. null = never evaluated.
  capture_status?: { fire: boolean; reason: string } | null;
  // Track B B1(2) — multi-KG: the session's grounding project SET (world +
  // member books) unioned into one memory block. Empty = the legacy
  // single-project (project_id) path. ≥2 → the "multi" memory mode.
  project_ids?: string[];
  // A2A phase-2: optional "composer" model. When set, the orchestrator
  // (model_ref) can call compose_prose, which streams THIS model for prose.
  composer_model_source?: string | null;
  composer_model_ref?: string | null;
  // D-PLAN-PLANNER-DEFAULT-FE phase 2: optional per-session planner model.
  planner_model_source?: string | null;
  planner_model_ref?: string | null;
  // Chat & AI settings, SESSION tier — the RAW override stored on this session, not
  // the resolved cascade. `null`/`{}` means "no override here → inherited". The tier
  // chip needs this to tell "set HERE" from "inherited"; value-equality with the
  // parent tier is NOT the same thing (spec §3.1, finding UX-5).
  grounding_enabled?: boolean | null;
  voice_overrides?: Record<string, unknown>;
  context_overrides?: Record<string, unknown>;
  // K-CLEAN-5 (D-K8-04): memory mode for the chat header
  // MemoryIndicator.
  //   no_project — no project linked, AI sees only the global bio
  //   static     — project linked, AI sees its summary + glossary
  //   degraded   — knowledge-service was unreachable on the last
  //                turn and chat-service fell back to recent-only
  // GET responses populate from `project_id` (no_project | static | multi).
  // The SSE stream emits a `memory-mode` event on every turn so the
  // FE can flip to `degraded` when the upstream call falls back.
  //   multi — a set of ≥2 knowledge graphs unioned into one context.
  memory_mode?: 'no_project' | 'static' | 'degraded' | 'multi';
  // Story 04: session-scoped tool/skill curation (empty = auto-discovery).
  enabled_tools?: string[];
  enabled_skills?: string[];
  activated_tools?: string[];
  // Tool-catalog-simplification Part D (CAT-4): legacy (superseded,
  // find_tools-invisible) tools the user manually pinned for THIS session.
  pinned_legacy_tools?: string[];
  // W3 — manual steerable compact: messages with sequence_num below this are
  // represented server-side by a stored summary on every later turn.
  // null/absent = never manually compacted. Drives the panel's
  // "compacted through message N" line.
  compacted_before_seq?: number | null;
}

// W3 — POST /v1/chat/sessions/{id}/compact response (all token counts are the
// backend's script-aware estimates, not provider-measured).
export interface CompactSessionResult {
  summary_tokens: number;
  compacted_message_count: number;
  /** null only on a clear (cleared=true) — a compact always sets it. */
  compacted_before_seq: number | null;
  tokens_before_estimate: number;
  tokens_after_estimate: number;
  /** true when the request cleared the stored compact instead of compacting. */
  cleared?: boolean;
}

/** Story 04 / #07b — agentSurface SSE payload (inspector state machine). */
export type AgentSurfacePhase =
  | 'Idle'
  | 'Curated'
  | 'SkillInjected'
  | 'Discovering'
  | 'Activated'
  | 'ToolRunning';

/** W6 additive — the advertised tool surface of the last provider pass,
 *  split core (always-on) / frontend (surface extras) / activated (discovered
 *  or hot-seeded server tools with full schemas). */
export interface AgentSurfaceAdvertised {
  core: string[];
  frontend: string[];
  activated: string[];
}

export interface AgentSurfaceState {
  phase: AgentSurfacePhase;
  pinned_count: number;
  hot_seed_count: number;
  activated_count: number;
  injected_skills: string[];
  running_tool: string | null;
  last_find_tools_query: string | null;
  find_tools_call_count: number;
  // W6 — STRICTLY ADDITIVE (an older backend omits them; render degrades):
  /** advertised names per bucket on the last provider pass. */
  advertised?: AgentSurfaceAdvertised;
  /** per-MCP-server grouping of the advertised surface: key → {tools: N}.
   *  Keys mirror chat-service agent_surface.server_key_for_tool. */
  servers?: Record<string, { tools: number }>;
  /** W1 schema-token measurement split (frontend vs server/MCP schemas). */
  schema_tokens?: { frontend: number; mcp: number };
}

// RAID Wave A3 — the context-budget snapshot the backend emits as an AG-UI
// CUSTOM event (`name:"contextBudget"`) on every turn finish. Drives the chat
// header ContextMeter. `pct` = used/effective; null when the model has no
// registered context_length (so we render "—" instead of a bogus %).
//
// Chat Quality Wave W1/W2 — STRICTLY ADDITIVE fields: `breakdown` (per-category
// token map, fixed 12-key vocabulary mirroring chat-service
// token_budget.BREAKDOWN_CATEGORIES), `baseline_tokens` (fixed overhead before
// the first user word) and `until_compact_pct` (headroom to the auto-compact
// trigger, in pct-of-effective-limit points). All optional — an older backend
// (or the resume path, which doesn't re-measure parts) omits them and the
// meter renders exactly as before.

/** The one nested breakdown entry: knowledge memory total + per-section split
 *  (glossary_entities / facts / passages / summaries / instructions / …). */
export interface MemoryKnowledgeBreakdown {
  total: number;
  sections: Record<string, number>;
}

/** Per-category context tokens. Keys mirror the backend BREAKDOWN_CATEGORIES
 *  vocabulary; every key is present (0 when absent this turn) on a W1 backend. */
export interface ContextBreakdownMap {
  system_prompt?: number;
  memory_knowledge?: MemoryKnowledgeBreakdown;
  /** T4 cached story-bible safety-net block (D4; 0 unless projected on a degraded turn). */
  story_state?: number;
  working_memory?: number;
  steering?: number;
  skills?: number;
  plan_nudge?: number;
  book_note?: number;
  attached_context?: number;
  history?: number;
  tool_results?: number;
  frontend_tool_schemas?: number;
  mcp_tool_schemas?: number;
  // Context Budget Law forward-declared allocation categories (present 0 until
  // their tier populates them): rolling summary (T6), whitelisted chapter body
  // (D3), model reasoning budget (D7). Mirrors the BE BREAKDOWN_CATEGORIES vocabulary
  // (chat-service token_budget.py; parity pinned via contracts/context-trace.contract.json).
  summary?: number;
  chapter?: number;
  reasoning?: number;
}

export interface ContextBudget {
  used_tokens: number;
  context_length: number | null;
  effective_limit: number | null;
  pct: number | null;
  /** W1 additive — per-category token breakdown (drill-down panel). */
  breakdown?: ContextBreakdownMap | null;
  /** W1 additive — tokens present before the first user word (system + tools). */
  baseline_tokens?: number | null;
  /** W1 additive — pct-points of headroom until the auto-compact trigger. */
  until_compact_pct?: number | null;
}

// Chat Quality Wave W1-residual — one point of the per-turn context-token
// HISTORY series (GET /v1/chat/sessions/{id}/context-history). Mirrors the BE
// ContextHistoryPoint: the persisted per-category breakdown of one assistant
// turn, so the panel can chart how each category evolved across the session.
export interface ContextHistoryPoint {
  sequence_num: number;
  created_at: string;
  input_tokens: number | null;
  output_tokens: number | null;
  /** Same category vocabulary as the live budget's breakdown (memory_knowledge
   *  nests {total, sections}). */
  breakdown: ContextBreakdownMap;
}

// ── Context Compiler · Trace Inspector (spec §11) ──────────────────────────────
// The Inspector reads the FULL persisted contextBudget frame per turn (not just
// the breakdown sub-map the chart uses). These mirror chat-service:
// token_budget.context_budget_event + loreweave_context.TraceSpan.

/** One Planner/Compiler decision (the compile-trace waterfall row). `delta` < 0 =
 *  tokens SAVED, > 0 = INCLUDED, 0 = neutral; `is_error` = a reject span. */
export interface TraceSpanFrame {
  phase: 'planner' | 'compiler';
  tier: string; // T0..T6
  category: string;
  action: string;
  delta: number;
  is_error: boolean;
}

/** The T5 entity-presence gate decision surfaced per turn. */
export interface EntityPresenceFrame {
  grounding_needed: boolean;
  matched: string[];
  reason: string;
}

/** Prompt-caching metrics for this turn (chat-service `caching_monitor.build_caching_metrics`
 *  + the rolling `detect_thrashing` verdict). All numeric fields are always present (0 /
 *  "stateless" when nothing cached); `thrashing` is `null` when a verdict isn't meaningful yet
 *  (auto-cache provider, or fewer than 3 turns of history). */
export interface CachingFrame {
  strategy: string;
  auto_prefix: boolean;
  create_tok: number;
  read_tok: number;
  uncached_tok: number;
  hit_rate: number;
  cost_delta_ratio: number;
  write_premium_tok: number;
  net_negative: boolean;
  thrashing: boolean | null;
}

/** The full persisted contextBudget frame — a superset of ContextBudget with the
 *  §11a Inspector telemetry. Every Inspector-specific field is optional so an
 *  older/pre-M1 turn (no telemetry) still renders (blank chips, no waterfall). */
export interface ContextTraceFrame extends ContextBudget {
  target?: number | null;
  pct_of_target?: number | null;
  raw_tokens?: number | null;
  reduction_pct?: number | null;
  status_flags?: string[];
  retrieval_mode?: string | null;
  intent?: string | null;
  entity_presence?: EntityPresenceFrame | null;
  trace?: TraceSpanFrame[];
  caching?: CachingFrame | null;
}

/** One turn in the Inspector series (GET /v1/chat/sessions/{id}/context-trace).
 *  Mirrors the BE ContextTracePoint: the full frame + the user message that drove it. */
export interface ContextTracePoint {
  sequence_num: number;
  created_at: string;
  input_tokens: number | null;
  output_tokens: number | null;
  user_message: string | null;
  frame: ContextTraceFrame;
}

// Chat Quality Wave W1/W2 — the `compaction` CUSTOM frame, emitted when
// in-loop compaction actually changed the prompt (CompactionReport.to_event()).
// Feeds the "earlier turns compacted" toast.
export interface CompactionEvent {
  triggered: boolean;
  tool_results_cleared: number;
  turns_truncated: number;
  summarized: boolean;
  summarize_failed: boolean;
  overflowed: boolean;
  tokens_before: number;
  tokens_after: number;
  steps?: string[];
}

export interface ToolCatalogItem {
  name: string;
  domain: string;
  tier: string;
  description: string;
  /** CAT-4: 'discoverable' (default) or 'legacy' (superseded — only pinnable
   *  via pinned_legacy_tools, GET .../tools/catalog?visibility=legacy). */
  visibility?: 'discoverable' | 'legacy';
}

export interface SkillCatalogItem {
  id: string;
  label: string;
  surfaces: string[];
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
  // D-COMPOSE-SESSION-RESTORE: tag a book-scoped session at creation time
  // (known upfront, unlike project_id which is bound after the fact) so it
  // can be found again on the next Compose open regardless of whether a
  // knowledge project exists for the book.
  book_id?: string;
  // T-4 / WS-1.10: the Work Assistant creates 'assistant' sessions (the discriminator
  // recall + capture gate on); every other host omits it → server defaults to 'chat'.
  session_kind?: 'chat' | 'assistant';
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
  // Track B B1(2) — multi-KG: set/replace the grounding project SET. Presence
  // in the body drives the write (an explicit [] clears it back to the legacy
  // single-project path); omitted leaves it alone.
  project_ids?: string[];
  // A2A phase-2: set/clear the composer model. Same model_fields_set
  // semantics as project_id — emit explicit null to clear.
  composer_model_source?: string | null;
  composer_model_ref?: string | null;
  // D-PLAN-PLANNER-DEFAULT-FE phase 2: set/clear the per-session planner model.
  planner_model_source?: string | null;
  planner_model_ref?: string | null;
  enabled_tools?: string[];
  enabled_skills?: string[];
  activated_tools?: string[] | null;
  pinned_legacy_tools?: string[] | null;
  // Chat & AI settings, SESSION tier (spec 2026-07-05 §3.5). Same 3-state contract as
  // project_id: omit to leave alone, explicit `null` to CLEAR the override (inherit from
  // Book/Account/System), a value to override for this session. `undefined` is dropped by
  // JSON.stringify — which is exactly "omitted" — so a clear MUST be an explicit null.
  grounding_enabled?: boolean | null;
  voice_overrides?: Record<string, unknown> | null;
  context_overrides?: Record<string, unknown> | null;
}
