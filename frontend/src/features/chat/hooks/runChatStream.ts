// L-chat (T5.4 M2 / D-T5.4-CHAT-HOIST) — the PURE cowriter chat stream core.
//
// Lifted verbatim (behavior-for-behavior) from useChatMessages.streamPost so the
// SAME fetch / AG-UI parse / accumulator logic runs in BOTH places without
// divergence:
//   • in-process (the hook's default path — byte-identical to pre-M2),
//   • inside the SharedWorker (chatLiveState.shared-worker), which owns ONE chat
//     turn and fans these same events to every window's port (survives the
//     opener closing).
// No React, no DOM, no timers — safe to import in a worker. The thinking-elapsed
// timer + setState live in the consumer (hook/hub); this core only EMITS phase
// transitions + state facets through the `ChatCallbacks` sink. `apiBase()` is ''
// (relative), which a worker resolves against its own same-origin script URL, so
// the gateway proxy path is identical to the main thread.
//
// ⚠ CRITICAL (review-impl): this core must preserve EVERY AG-UI event path the
// inline switch handled — a dropped event type is a silent regression. The 7
// handled cases + 9 framing no-ops are enumerated below exactly as the original.
import { chatApi } from '../api';
import { AgUiEventType } from './agUiEvents';
import type {
  CustomEvent as AgUiCustomEvent,
  ReasoningMessageContentEvent,
  RunErrorEvent,
  RunFinishedEvent,
  TextMessageContentEvent,
  ToolCallResultEvent,
  ToolCallStartEvent,
} from './agUiEvents';
import type { ActivityEvent, ChatMessage, ToolCallRecord, AgentSurfaceState, ContextBudget, CompactionEvent } from '../types';
import type { EffortLevel } from '@/components/ai-task/effort';

export type StreamPhase = 'idle' | 'thinking' | 'responding';

/** The effort dropdown's wire value — the unified 5-level vocabulary (the same
 *  `EffortLevel`) the message POST carries as `reasoning_effort`; chat-service maps
 *  it into the reasoning pipeline (`auto` → adaptive/omit). */
export type ReasoningEffortLevel = EffortLevel;

/** The per-turn request inputs lifted out of the hook's closure. Everything
 *  streamPost read from props/args is now an explicit field, so the core is a
 *  pure function of its arguments (worker-safe — no React closure). */
export type ChatStreamArgs = {
  sessionId: string;
  content: string;
  editFromSequence?: number;
  thinking?: boolean;
  // W4 — granular effort from the input-bar dropdown. Sent as `reasoning_effort`
  // on the message POST (chat-service maps it to the model's reasoning knob).
  reasoningEffort?: ReasoningEffortLevel;
  editorContext?: { book_id: string; chapter_id: string };
  // #09 Lane A — presence tells chat-service to advertise the studio dock-nav frontend tools.
  studioContext?: { book_id?: string; project_id?: string; active_chapter_id?: string; active_panel_ids?: string[]; context_revision?: number };
  composeMode?: boolean;
  bookContext?: { book_id: string };
  displayLanguage?: string;
  enabledTools?: string[];
  enabledSkills?: string[];
  // RAID C2 (DR-C2): HITL permission mode — 'ask' filters the server-tool
  // surface to reads; 'write' (default, omitted) is today's behavior + the
  // Tier-A prompt-once approval gate. Distinct from composeMode (disable_tools).
  // RAID B2 (07S §5b): 'plan' = the ask surface + the PlanForge plan_* tools
  // (plan artifacts, never prose).
  permissionMode?: 'ask' | 'plan' | 'write';
  // ARCH-1 C6: when set, POST this descriptor instead of the messages endpoint
  // (the resume / tool-result path). The consume loop is identical, so send +
  // resume share all stream handling.
  override?: { url: string; body: Record<string, unknown> };
};

/** Memory-mode wire values (CUSTOM{name:'memoryMode'}). */
export type MemoryMode = 'no_project' | 'static' | 'degraded';

/** The terminal payload — the fully-assembled assistant turn + run metadata.
 *  The consumer maps this onto a ChatMessage (it owns `messages.length` for the
 *  sequence number, which is React state and stays main-thread). */
export type ChatStreamResult = {
  content: string;
  reasoning: string;
  toolCalls: ToolCallRecord[];
  activities: ActivityEvent[];
  messageId: string | null;
  usage: { promptTokens?: number; completionTokens?: number };
  timing: { responseTimeMs?: number; timeToFirstTokenMs?: number };
};

/** Event sink — the hook maps these to setState (+ refs); the hub maps them to a
 *  snapshot it fans to all ports. One callback per state facet so neither side
 *  has to re-parse. */
export type ChatCallbacks = {
  /** Phase transition (thinking | responding). Drives the elapsed timer owner. */
  onPhase?: (phase: StreamPhase) => void;
  /** A reasoning delta arrived; `accumulated` is the full reasoning so far. */
  onReasoning?: (accumulated: string, delta: string) => void;
  /** A text/content delta arrived; `accumulated` is the full content so far. */
  onText?: (accumulated: string, delta: string) => void;
  /** A resolved tool-call record (memory tool RESULT, or a suspended frontend tool). */
  onToolCall?: (record: ToolCallRecord) => void;
  /** A Tier-A auto-applied op (CUSTOM activity) for the Undo strip. */
  onActivity?: (activity: ActivityEvent) => void;
  /** CUSTOM memoryMode → flip the header indicator. */
  onMemoryMode?: (mode: MemoryMode) => void;
  /** CUSTOM composing on/off → the transient "✍️ Drafting…" indicator. */
  onComposing?: (active: boolean) => void;
  /** Story 04: CUSTOM agentSurface → runtime inspector reducer. */
  onAgentSurface?: (state: AgentSurfaceState) => void;
  /** RAID Wave A3: CUSTOM contextBudget → the chat header context-used meter. */
  onContextBudget?: (budget: ContextBudget) => void;
  /** W2: CUSTOM compaction → the "earlier turns compacted" toast. Fired only
   *  when the backend's in-loop compaction actually changed the prompt. */
  onCompaction?: (event: CompactionEvent) => void;
  /** A run-level error (RUN_ERROR, or a non-OK response). */
  onError?: (message: string) => void;
  /** Terminal — the assembled assistant turn. Fired on a clean stream end. */
  onEnd?: (result: ChatStreamResult) => void;
  /** Aborted (stop / supersede / unmount). `partial` = what assembled so far,
   *  so the consumer can mirror the legacy AbortError return value. */
  onAbort?: (partial: ChatStreamResult) => void;
};

/** Build the request URL + body. Mirrors streamPost's body assembly exactly —
 *  including the editor/book/display/compose conditional fields and the
 *  override (resume) short-circuit. */
function buildRequest(args: ChatStreamArgs): { url: string; body: Record<string, unknown> } {
  if (args.override) return { url: args.override.url, body: args.override.body };

  const body: Record<string, unknown> = { content: args.content };
  if (args.editFromSequence != null) body.edit_from_sequence = args.editFromSequence;
  if (args.thinking != null) body.thinking = args.thinking;
  // W4: only sent when the user picked a granular effort (today: Deep). Fast /
  // Standard stay on the legacy `thinking` boolean so the wire is unchanged
  // for existing behavior.
  if (args.reasoningEffort != null) body.reasoning_effort = args.reasoningEffort;
  // ARCH-1 C6: editor panel → advertise the write-back frontend tool + carry
  // which chapter the assistant is editing.
  if (args.editorContext) body.editor_context = args.editorContext;
  if (args.studioContext) body.studio_context = args.studioContext;
  // Glossary-assistant P3: book-scoped (non-editor) chat → advertise the
  // glossary edit-existing frontend tool.
  if (args.bookContext) body.book_context = args.bookContext;
  // S6: forward the per-book display language so knowledge composes entity
  // aliases in it (omitted when not viewing a translation → source aliases).
  if (args.displayLanguage) body.display_language = args.displayLanguage;
  if (args.enabledTools?.length) body.enabled_tools = args.enabledTools;
  if (args.enabledSkills?.length) body.enabled_skills = args.enabledSkills;
  // Compose mode: prose-only turn, no tool advertising (server-side gate).
  if (args.composeMode) body.disable_tools = true;
  // RAID C2/B2: only send a non-default mode — omitting means 'write'
  // server-side, keeping the wire byte-identical for existing behavior.
  if (args.permissionMode === 'ask' || args.permissionMode === 'plan') {
    body.permission_mode = args.permissionMode;
  }

  return { url: chatApi.messagesUrl(args.sessionId), body };
}

/**
 * Run one chat turn: POST → consume the AG-UI SSE stream → emit through `cb`.
 * Resolves with the assembled result when the run finishes (clean end).
 *
 * Contract preserved from streamPost:
 *  - On a non-OK response → throws `${status}: ${detail}` (caller shows error).
 *  - On RUN_ERROR → throws the server message (the error path refetches).
 *  - On abort → fires `onAbort(partial)` and RESOLVES with the partial (does not
 *    throw) — the legacy AbortError branch returned accumulatedContent.
 *  - On clean end → fires `onEnd(result)` and resolves with the full result.
 *  - reader.cancel() is wired to the abort signal (the SSE-cancel gotcha).
 */
export async function runChatStream(
  args: ChatStreamArgs,
  token: string | null,
  cb: ChatCallbacks,
  signal: AbortSignal,
): Promise<ChatStreamResult> {
  let accumulatedContent = '';
  let accumulatedReasoning = '';
  // K21-C (D2): per-turn tool-call list, accumulated from the tool-call SSE
  // frames. Attached to the appended assistantMessage so the indicator works
  // from the live stream without a refetch.
  const accumulatedToolCalls: ToolCallRecord[] = [];
  // MCP fan-out (C-ACTIVITY): Tier-A auto-applied ops streamed this turn.
  const accumulatedActivities: ActivityEvent[] = [];
  // ARCH-1 C4: AG-UI frames a tool call across TOOL_CALL_START (name) and
  // TOOL_CALL_RESULT (ok). Hold the name by toolCallId between the two.
  const openToolCalls = new Map<string, string>();
  // ARCH-1 C6: accumulate TOOL_CALL_ARGS per id so a frontend tool's proposal
  // payload (operation/text) reaches the chip.
  const openToolArgs = new Map<string, string>();
  let streamMessageId: string | null = null;
  let streamUsage: { promptTokens?: number; completionTokens?: number } = {};
  let streamTiming: { responseTimeMs?: number; timeToFirstTokenMs?: number } = {};

  const assemble = (): ChatStreamResult => ({
    content: accumulatedContent,
    reasoning: accumulatedReasoning,
    toolCalls: accumulatedToolCalls,
    activities: accumulatedActivities,
    messageId: streamMessageId,
    usage: streamUsage,
    timing: streamTiming,
  });

  const { url, body } = buildRequest(args);

  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token ?? ''}`,
        // ARCH-1 C4: request the AG-UI event protocol (chat-service C3). The
        // backend defaults to the legacy vocabulary for any client that doesn't
        // send this, so other consumers are unaffected.
        'x-loreweave-stream-format': 'agui',
      },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    // A fetch that rejects with AbortError (stop/supersede) mirrors the legacy
    // AbortError branch: fire onAbort + resolve with the partial, don't throw.
    if ((err as Error).name === 'AbortError') {
      cb.onAbort?.(assemble());
      return assemble();
    }
    throw err;
  }

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  // Explicitly cancel the reader on abort — do NOT rely on fetch propagating the
  // abort to the stream. If it doesn't (mocked fetch in tests, or some
  // runtimes), the pending read() below never resolves and the loop leaks
  // forever. cancel() ends read() with {done:true}. (feedback_sse_reader_must_cancel_on_abort)
  const cancelReader = () => void reader.cancel().catch(() => {});
  if (signal.aborted) cancelReader();
  else signal.addEventListener('abort', cancelReader, { once: true });

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') continue;

        try {
          // ARCH-1 C4: the stream speaks the AG-UI protocol. Map each AG-UI
          // event onto the same internal accumulators/phases the legacy parser
          // drove, so every consumer is unaffected. Framing-only events
          // (RUN_STARTED, TEXT_MESSAGE_START/END, REASONING_* boundaries,
          // TOOL_CALL_END) need no handling — the phase transitions lazily on
          // the first content delta.
          const event = JSON.parse(payload) as { type?: string };
          switch (event.type) {
            // ── 1. REASONING_MESSAGE_CONTENT — thinking deltas ──────────────
            case AgUiEventType.REASONING_MESSAGE_CONTENT: {
              const delta = (event as ReasoningMessageContentEvent).delta;
              if (!delta) break;
              if (accumulatedReasoning === '') {
                cb.onPhase?.('thinking');
              }
              accumulatedReasoning += delta;
              cb.onReasoning?.(accumulatedReasoning, delta);
              break;
            }
            // ── 2. TEXT_MESSAGE_CONTENT — answer deltas ─────────────────────
            case AgUiEventType.TEXT_MESSAGE_CONTENT: {
              const delta = (event as TextMessageContentEvent).delta;
              if (!delta) break;
              if (accumulatedContent === '' && accumulatedReasoning !== '') {
                // Transition from thinking → responding
                cb.onPhase?.('responding');
              } else if (accumulatedContent === '') {
                cb.onPhase?.('responding');
              }
              accumulatedContent += delta;
              cb.onText?.(accumulatedContent, delta);
              break;
            }
            // ── 3. TOOL_CALL_START — hold the name until RESULT resolves ─────
            case AgUiEventType.TOOL_CALL_START: {
              const e = event as ToolCallStartEvent;
              if (e.toolCallId) openToolCalls.set(e.toolCallId, e.toolCallName);
              break;
            }
            // ── 4. TOOL_CALL_ARGS — accumulate args per id ──────────────────
            case AgUiEventType.TOOL_CALL_ARGS: {
              const e = event as { toolCallId?: string; delta?: string };
              if (e.toolCallId) {
                openToolArgs.set(e.toolCallId, (openToolArgs.get(e.toolCallId) ?? '') + (e.delta ?? ''));
              }
              break;
            }
            // ── 5. TOOL_CALL_RESULT — one chip per executed memory tool ─────
            case AgUiEventType.TOOL_CALL_RESULT: {
              // The server encodes the authoritative outcome as {ok, result|error}
              // inside content (chat-service C3) — read `ok` directly rather than
              // inferring it from payload shape, so a tool result that legitimately
              // contains an "error" field can't be misread as a failure.
              const e = event as ToolCallResultEvent;
              const tool = openToolCalls.get(e.toolCallId);
              if (tool === undefined) break; // RESULT without a START — skip
              openToolCalls.delete(e.toolCallId);
              let ok = true;
              let result: unknown;
              try {
                const parsed = JSON.parse(e.content);
                result = parsed;
                if (parsed && typeof parsed === 'object' && parsed.ok === false) {
                  ok = false;
                }
              } catch {
                // non-JSON content → treat as a successful opaque result
                result = e.content;
              }
              // Keep the parsed result on the record (matches the replay shape from
              // the tool_calls JSONB). AssistantMessage reads it to auto-render a
              // confirm card when a class-C propose tool minted a confirm_token but
              // the model never called the frontend confirm tool.
              const record: ToolCallRecord = { tool, ok, result };
              accumulatedToolCalls.push(record);
              cb.onToolCall?.(record);
              break;
            }
            // ── 6. CUSTOM — memoryMode/persisted/composing/activity/agentSurface/contextBudget/compaction
            case AgUiEventType.CUSTOM: {
              const e = event as AgUiCustomEvent;
              if (e.name === 'memoryMode') {
                // K-CLEAN-5 (D-K8-04): flip the header memory indicator.
                const mode = e.value?.mode;
                if (mode) cb.onMemoryMode?.(mode as MemoryMode);
              } else if (e.name === 'persisted') {
                // The saved message id (+ output id / has_reasoning).
                streamMessageId = (e.value?.messageId as string) || null;
              } else if (e.name === 'composing') {
                // A2A phase-2: the composer model is drafting (on/off).
                cb.onComposing?.(!!e.value?.active);
              } else if (e.name === 'activity') {
                // MCP fan-out (C-ACTIVITY): a Tier-A auto-applied op. The value
                // carries {op, summary, undo}. Accumulate for the Undo strip.
                const a = e.value as unknown as ActivityEvent;
                if (a && typeof a.op === 'string' && typeof a.summary === 'string') {
                  const activity: ActivityEvent = {
                    op: a.op,
                    summary: a.summary,
                    ...(a.undo ? { undo: a.undo } : {}),
                  };
                  accumulatedActivities.push(activity);
                  cb.onActivity?.(activity);
                }
              } else if (e.name === 'agentSurface') {
                const payload = e.value as unknown as AgentSurfaceState;
                if (payload && typeof payload.phase === 'string') {
                  cb.onAgentSurface?.(payload);
                }
              } else if (e.name === 'contextBudget') {
                // RAID Wave A3: turn-finish context usage → header meter. Guard on
                // used_tokens being a number so a malformed frame can't crash the
                // meter; pct/limits may legitimately be null (unregistered model).
                // W1/W2 additive fields (breakdown / baseline_tokens /
                // until_compact_pct) pass through when present — an older backend
                // omits them and the meter renders exactly as before.
                const v = e.value as unknown as ContextBudget;
                if (v && typeof v.used_tokens === 'number') {
                  cb.onContextBudget?.({
                    used_tokens: v.used_tokens,
                    context_length: typeof v.context_length === 'number' ? v.context_length : null,
                    effective_limit: typeof v.effective_limit === 'number' ? v.effective_limit : null,
                    pct: typeof v.pct === 'number' ? v.pct : null,
                    ...(v.breakdown && typeof v.breakdown === 'object' ? { breakdown: v.breakdown } : {}),
                    ...(typeof v.baseline_tokens === 'number' ? { baseline_tokens: v.baseline_tokens } : {}),
                    ...(typeof v.until_compact_pct === 'number' ? { until_compact_pct: v.until_compact_pct } : {}),
                  });
                }
              } else if (e.name === 'compaction') {
                // W2: in-loop compaction did work this turn → toast. Guard on the
                // token counters being numbers so a malformed frame is dropped
                // instead of crashing the stream.
                const v = e.value as unknown as CompactionEvent;
                if (v && typeof v.tokens_before === 'number' && typeof v.tokens_after === 'number') {
                  cb.onCompaction?.({
                    triggered: !!v.triggered,
                    tool_results_cleared: typeof v.tool_results_cleared === 'number' ? v.tool_results_cleared : 0,
                    turns_truncated: typeof v.turns_truncated === 'number' ? v.turns_truncated : 0,
                    summarized: !!v.summarized,
                    summarize_failed: !!v.summarize_failed,
                    overflowed: !!v.overflowed,
                    tokens_before: v.tokens_before,
                    tokens_after: v.tokens_after,
                    ...(Array.isArray(v.steps) ? { steps: v.steps } : {}),
                  });
                }
              }
              break;
            }
            // ── 7. RUN_FINISHED — usage/timing + suspended-run/pendingToolCall
            case AgUiEventType.RUN_FINISHED: {
              const result = (event as RunFinishedEvent).result as
                | (RunFinishedEvent['result'] & {
                    status?: string;
                    pendingToolCall?: { runId: string; toolCallId: string; toolName: string };
                  })
                | undefined;
              streamUsage = result?.usage || {};
              streamTiming = result?.timing || {};
              // ARCH-1 C6: a suspended run — a frontend tool (propose_edit) is
              // awaiting the user's apply/dismiss. Record the pending call + push
              // a frontend-tool chip carrying the proposal args so the UI can
              // render Apply/Dismiss.
              if (result?.status === 'suspended' && result.pendingToolCall) {
                const p = result.pendingToolCall;
                let parsedArgs: Record<string, unknown> = {};
                try {
                  parsedArgs = JSON.parse(openToolArgs.get(p.toolCallId) ?? '{}');
                } catch {
                  parsedArgs = {};
                }
                const record: ToolCallRecord = {
                  tool: p.toolName,
                  ok: true,
                  pending: true,
                  runId: p.runId,
                  toolCallId: p.toolCallId,
                  args: parsedArgs,
                };
                accumulatedToolCalls.push(record);
                cb.onToolCall?.(record);
              }
              break;
            }
            // ── RUN_ERROR — throw the server message ────────────────────────
            case AgUiEventType.RUN_ERROR: {
              throw new Error((event as RunErrorEvent).message || 'Stream error');
            }
            // RUN_STARTED + all framing-only events (TEXT_MESSAGE_START/END,
            // REASONING_START/MESSAGE_START/MESSAGE_END/END, TOOL_CALL_END):
            // no-op. (9 framing events; the phase transitions lazily.)
            default:
              break;
          }
        } catch (parseErr) {
          if (parseErr instanceof SyntaxError) continue; // partial/garbled frame
          throw parseErr; // RUN_ERROR (or any thrown handler error)
        }
      }
    }
  } catch (err) {
    // An abort surfacing through read() (real aborted fetch) → mirror the legacy
    // AbortError branch: onAbort + resolve with the partial, don't throw.
    if ((err as Error).name === 'AbortError' || signal.aborted) {
      cb.onAbort?.(assemble());
      return assemble();
    }
    throw err; // RUN_ERROR / network error → caller's error path
  }

  // Clean end — assemble + emit the terminal result.
  const finalResult = assemble();
  cb.onEnd?.(finalResult);
  return finalResult;
}

/** Build the appended assistant ChatMessage from a stream result. Lifted out of
 *  streamPost so the inline hook AND the worker consumer assemble it identically.
 *  `sessionId` + `sequenceNum` are React/local state the caller owns. */
export function assembleAssistantMessage(
  result: ChatStreamResult,
  sessionId: string,
  sequenceNum: number,
  // DBT-CHAT-PERSIST — 'interrupted' | 'error' when the turn was stopped/failed,
  // so the seamlessly-appended bubble carries the incomplete badge immediately
  // (the backend also persists it, but that refetch races the append). Defaults
  // to 'stop' (a clean completion).
  finishReason: 'stop' | 'interrupted' | 'error' = 'stop',
): ChatMessage {
  return {
    message_id: result.messageId || `done-${Date.now()}`,
    session_id: sessionId,
    owner_user_id: '',
    role: 'assistant',
    content: result.content,
    content_parts: {
      ...(result.reasoning
        ? { reasoning: result.reasoning, reasoning_length: result.reasoning.length }
        : {}),
      ...(result.timing.responseTimeMs != null ? { response_time_ms: result.timing.responseTimeMs } : {}),
      ...(result.timing.timeToFirstTokenMs != null
        ? { time_to_first_token_ms: result.timing.timeToFirstTokenMs }
        : {}),
    },
    sequence_num: sequenceNum,
    branch_id: 0,
    input_tokens: result.usage.promptTokens ?? null,
    output_tokens: result.usage.completionTokens ?? null,
    model_ref: null,
    is_error: finishReason === 'error',
    error_detail: null,
    finish_reason: finishReason,
    parent_message_id: null,
    created_at: new Date().toISOString(),
    // K21-C (D2): attach the accumulated tool calls so the ToolCallIndicator
    // renders from the live stream. null when the turn made no tool calls.
    tool_calls: result.toolCalls.length > 0 ? result.toolCalls : null,
    // MCP fan-out (C-ACTIVITY): Tier-A ops streamed this turn → Undo strip.
    activities: result.activities.length > 0 ? result.activities : null,
  };
}
