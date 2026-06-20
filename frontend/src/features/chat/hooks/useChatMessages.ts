import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ActivityEvent, ChatMessage, ToolCallRecord } from '../types';
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

type StreamStatus = 'idle' | 'streaming' | 'error';
type StreamPhase = 'idle' | 'thinking' | 'responding';

/** Delta type emitted during SSE streaming */
export type StreamDeltaType = 'content' | 'reasoning';
/** Callback for each SSE delta token */
export type OnStreamDelta = (delta: string, type: StreamDeltaType) => void;
/** K-CLEAN-5 (D-K8-04): callback fired when the stream's first
 *  `memory-mode` event arrives. ChatSessionContext registers this so
 *  the chat header MemoryIndicator can flip to a degraded badge as
 *  soon as chat-service signals the knowledge call fell back. */
export type OnMemoryMode = (mode: 'no_project' | 'static' | 'degraded') => void;

/**
 * Unified hook: owns message list + SSE streaming for send/edit/regenerate.
 * Supports reasoning-delta (thinking) and text-delta (content) events.
 */
/** Outcome posted to the resume endpoint after the user acts on a frontend
 *  tool. propose_edit (prose) uses applied/dismissed; the glossary edit tool
 *  reports the REAL Apply result (H6) so the agent can't claim a false success. */
export type FrontendToolOutcome =
  | 'applied'
  | 'dismissed'
  | 'applied_saved'
  | 'applied_conflict'
  | 'applied_error'
  // Generalized class-C action confirm (spec §13) — supersedes the schema_* set
  | 'action_done'
  | 'token_expired'
  | 'action_error'
  | 'cancelled';

export function useChatMessages(
  sessionId: string | null,
  editorContext?: { book_id: string; chapter_id: string },
  /** Editor "Compose" mode: send `disable_tools` so the server advertises no
   *  tools this turn — the model writes prose to Apply manually (best for a
   *  reasoning model). Tools stay off until the user flips back to Agent. */
  composeMode?: boolean,
  /** Glossary-assistant P3: book-scoped chat (glossary page / reader) that is
   *  NOT the chapter editor. Enables the glossary edit-existing frontend tool. */
  bookContext?: { book_id: string },
) {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [streamPhase, setStreamPhase] = useState<StreamPhase>('idle');
  const [thinkingElapsed, setThinkingElapsed] = useState(0);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle');
  // A2A phase-2: true while the in-turn composer model is drafting prose
  // (compose_prose). Drives a transient "✍️ Drafting…" indicator.
  const [isComposing, setIsComposing] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const thinkingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const thinkingStartRef = useRef<number>(0);
  /** Settable callback for per-token deltas (used by voice mode pipeline) */
  const onStreamDeltaRef = useRef<OnStreamDelta | null>(null);
  /** Settable callback for when streaming ends (success or abort — not error) */
  const onStreamEndRef = useRef<(() => void) | null>(null);
  /** K-CLEAN-5 (D-K8-04): settable callback for the per-turn
   *  memory-mode SSE event from chat-service. */
  const onMemoryModeRef = useRef<OnMemoryMode | null>(null);

  // ── Fetch messages on session change ──────────────────────────────────────────

  const fetchMessages = useCallback(async (branchId?: number) => {
    if (!accessToken || !sessionId) {
      setMessages([]);
      return;
    }
    setIsLoading(true);
    try {
      const res = await chatApi.listMessages(accessToken, sessionId, undefined, branchId);
      setMessages(res.items);
    } catch {
      // Silently fail — toast is handled at component level
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, sessionId]);

  useEffect(() => {
    void fetchMessages();
  }, [fetchMessages]);

  // ── SSE streaming ─────────────────────────────────────────────────────────────

  const streamPost = useCallback(
    async (
      content: string,
      editFromSequence?: number,
      thinking?: boolean,
      // ARCH-1 C6: when set, POST this descriptor instead of the messages
      // endpoint (used by the resume / tool-result path). The consume loop is
      // identical, so send + resume share all stream handling.
      override?: { url: string; body: Record<string, unknown> },
    ): Promise<string> => {
      if (!accessToken || !sessionId) throw new Error('Not ready');

      // Abort any in-progress stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setStreamingText('');
      setStreamingReasoning('');
      setStreamPhase('idle');
      setThinkingElapsed(0);
      setStreamStatus('streaming');

      let accumulatedContent = '';
      let accumulatedReasoning = '';
      // K21-C (D2): per-turn tool-call list, accumulated from the
      // `tool-call` SSE event the same way reasoning/timing is. Attached
      // to the locally-appended assistantMessage so the indicator works
      // from the live stream without a refetch.
      const accumulatedToolCalls: ToolCallRecord[] = [];
      // MCP fan-out (C-ACTIVITY): Tier-A auto-applied ops streamed this turn as
      // CUSTOM{name:"activity"} events. Attached to the assistant message so the
      // Undo strip renders from the live stream like tool_calls.
      const accumulatedActivities: ActivityEvent[] = [];
      // ARCH-1 C4: AG-UI frames a tool call across TOOL_CALL_START (carries the
      // name) and TOOL_CALL_RESULT (carries ok). Hold the name by toolCallId
      // between the two so the resolved record is {tool, ok} like the legacy
      // `tool-call` event produced in one shot.
      const openToolCalls = new Map<string, string>();
      // ARCH-1 C6: accumulate TOOL_CALL_ARGS per id so a frontend tool's
      // proposal payload (operation/text) reaches the chip.
      const openToolArgs = new Map<string, string>();
      let streamMessageId: string | null = null;
      let streamUsage: { promptTokens?: number; completionTokens?: number } = {};
      let streamTiming: { responseTimeMs?: number; timeToFirstTokenMs?: number } = {};

      // Thinking timer
      function startThinkingTimer() {
        thinkingStartRef.current = Date.now();
        thinkingTimerRef.current = setInterval(() => {
          setThinkingElapsed((Date.now() - thinkingStartRef.current) / 1000);
        }, 100);
      }
      function stopThinkingTimer() {
        if (thinkingTimerRef.current) {
          clearInterval(thinkingTimerRef.current);
          thinkingTimerRef.current = null;
        }
      }

      try {
        const body: Record<string, unknown> = { content };
        if (editFromSequence != null) {
          body.edit_from_sequence = editFromSequence;
        }
        if (thinking != null) {
          body.thinking = thinking;
        }
        // ARCH-1 C6: editor panel → advertise the write-back frontend tool +
        // carry which chapter the assistant is editing.
        if (editorContext) {
          body.editor_context = editorContext;
        }
        // Glossary-assistant P3: book-scoped (non-editor) chat → advertise the
        // glossary edit-existing frontend tool. The editor panel already carries
        // editor_context (book_id); a glossary-page chat sends this instead.
        if (bookContext) {
          body.book_context = bookContext;
        }
        // Compose mode: prose-only turn, no tool advertising (server-side gate).
        if (composeMode) {
          body.disable_tools = true;
        }

        const res = await fetch(override?.url ?? chatApi.messagesUrl(sessionId), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
            // ARCH-1 C4: request the AG-UI event protocol (chat-service C3).
            // The backend defaults to the legacy vocabulary for any client
            // that doesn't send this, so other consumers are unaffected.
            'x-loreweave-stream-format': 'agui',
          },
          body: JSON.stringify(override?.body ?? body),
          signal: controller.signal,
        });

        if (!res.ok) {
          const detail = await res.text().catch(() => res.statusText);
          throw new Error(`${res.status}: ${detail}`);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error('No response body');

        // Explicitly cancel the reader on abort — do NOT rely on fetch
        // propagating the abort to the stream. If it doesn't (mocked fetch in
        // tests, or some runtimes), the pending read() below never resolves and
        // the loop leaks forever (process-exit hang). cancel() ends read() with
        // {done:true}. See feedback_sse_reader_must_cancel_on_abort.
        const cancelReader = () => void reader.cancel().catch(() => {});
        if (controller.signal.aborted) cancelReader();
        else controller.signal.addEventListener('abort', cancelReader, { once: true });

        const decoder = new TextDecoder();
        let buffer = '';

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
              // ARCH-1 C4: the stream now speaks the AG-UI protocol (chat
              // service C3). Map each AG-UI event onto the same internal
              // accumulators/phases the legacy parser drove, so every
              // consumer of this hook is unaffected. Framing-only events
              // (TEXT_MESSAGE_START/END, REASONING_* boundaries,
              // TOOL_CALL_ARGS/END) need no handling — the hook lazily
              // transitions phase on the first content delta.
              const event = JSON.parse(payload) as { type?: string };
              switch (event.type) {
                case AgUiEventType.REASONING_MESSAGE_CONTENT: {
                  const delta = (event as ReasoningMessageContentEvent).delta;
                  if (!delta) break;
                  if (accumulatedReasoning === '') {
                    setStreamPhase('thinking');
                    startThinkingTimer();
                  }
                  accumulatedReasoning += delta;
                  setStreamingReasoning(accumulatedReasoning);
                  onStreamDeltaRef.current?.(delta, 'reasoning');
                  break;
                }
                case AgUiEventType.TEXT_MESSAGE_CONTENT: {
                  const delta = (event as TextMessageContentEvent).delta;
                  if (!delta) break;
                  if (accumulatedContent === '' && accumulatedReasoning !== '') {
                    // Transition from thinking → responding
                    stopThinkingTimer();
                    setStreamPhase('responding');
                  } else if (accumulatedContent === '') {
                    setStreamPhase('responding');
                  }
                  accumulatedContent += delta;
                  setStreamingText(accumulatedContent);
                  onStreamDeltaRef.current?.(delta, 'content');
                  break;
                }
                case AgUiEventType.TOOL_CALL_START: {
                  // Hold the tool name until its RESULT resolves (AG-UI frames
                  // a tool call across START → … → RESULT).
                  const e = event as ToolCallStartEvent;
                  if (e.toolCallId) openToolCalls.set(e.toolCallId, e.toolCallName);
                  break;
                }
                case AgUiEventType.TOOL_CALL_ARGS: {
                  // ARCH-1 C6: accumulate args (one or more deltas) per id.
                  const e = event as { toolCallId?: string; delta?: string };
                  if (e.toolCallId) {
                    openToolArgs.set(e.toolCallId, (openToolArgs.get(e.toolCallId) ?? '') + (e.delta ?? ''));
                  }
                  break;
                }
                case AgUiEventType.TOOL_CALL_RESULT: {
                  // K21-C (D2): one chip per executed memory tool. The server
                  // encodes the authoritative outcome as {ok, result|error}
                  // inside content (chat-service C3) — we read `ok` directly
                  // rather than inferring it from payload shape, so a tool
                  // result that legitimately contains an "error" field can't be
                  // misread as a failure.
                  const e = event as ToolCallResultEvent;
                  const tool = openToolCalls.get(e.toolCallId);
                  if (tool === undefined) break; // RESULT without a START — skip
                  openToolCalls.delete(e.toolCallId);
                  let ok = true;
                  try {
                    const parsed = JSON.parse(e.content);
                    if (parsed && typeof parsed === 'object' && parsed.ok === false) {
                      ok = false;
                    }
                  } catch {
                    // non-JSON content → treat as a successful opaque result
                  }
                  accumulatedToolCalls.push({ tool, ok });
                  break;
                }
                case AgUiEventType.CUSTOM: {
                  const e = event as AgUiCustomEvent;
                  if (e.name === 'memoryMode') {
                    // K-CLEAN-5 (D-K8-04): flip the header memory indicator.
                    // Mode is 'no_project' | 'static' | 'degraded'.
                    const mode = e.value?.mode;
                    if (mode) onMemoryModeRef.current?.(mode as 'no_project' | 'static' | 'degraded');
                  } else if (e.name === 'persisted') {
                    // The saved message id (+ output id / has_reasoning).
                    streamMessageId = (e.value?.messageId as string) || null;
                  } else if (e.name === 'composing') {
                    // A2A phase-2: the composer model is drafting (on/off).
                    setIsComposing(!!e.value?.active);
                  } else if (e.name === 'activity') {
                    // MCP fan-out (C-ACTIVITY): a Tier-A auto-applied op. The
                    // value carries {op, summary, undo}. Accumulate for the
                    // Undo strip on the assistant message.
                    const a = e.value as unknown as ActivityEvent;
                    if (a && typeof a.op === 'string' && typeof a.summary === 'string') {
                      accumulatedActivities.push({
                        op: a.op,
                        summary: a.summary,
                        ...(a.undo ? { undo: a.undo } : {}),
                      });
                    }
                  }
                  break;
                }
                case AgUiEventType.RUN_FINISHED: {
                  const result = (event as RunFinishedEvent).result as
                    | (RunFinishedEvent['result'] & {
                        status?: string;
                        pendingToolCall?: { runId: string; toolCallId: string; toolName: string };
                      })
                    | undefined;
                  streamUsage = result?.usage || {};
                  streamTiming = result?.timing || {};
                  // ARCH-1 C6: a suspended run — a frontend tool (propose_edit)
                  // is awaiting the user's apply/dismiss. Record the pending
                  // call + push a frontend-tool chip carrying the proposal args
                  // so the UI can render Apply/Dismiss.
                  if (result?.status === 'suspended' && result.pendingToolCall) {
                    const p = result.pendingToolCall;
                    let parsedArgs: Record<string, unknown> = {};
                    try {
                      parsedArgs = JSON.parse(openToolArgs.get(p.toolCallId) ?? '{}');
                    } catch {
                      parsedArgs = {};
                    }
                    accumulatedToolCalls.push({
                      tool: p.toolName,
                      ok: true,
                      pending: true,
                      runId: p.runId,
                      toolCallId: p.toolCallId,
                      args: parsedArgs,
                    });
                  }
                  break;
                }
                case AgUiEventType.RUN_ERROR: {
                  throw new Error((event as RunErrorEvent).message || 'Stream error');
                }
                // RUN_STARTED + all framing-only events: no-op.
                default:
                  break;
              }
            } catch (parseErr) {
              if (parseErr instanceof SyntaxError) continue;
              throw parseErr;
            }
          }
        }

        stopThinkingTimer();
        setStreamStatus('idle');
        setStreamPhase('idle');

        // Seamless append: add completed assistant message to list without refetch
        const assistantMessage: ChatMessage = {
          message_id: streamMessageId || `done-${Date.now()}`,
          session_id: sessionId ?? '',
          owner_user_id: '',
          role: 'assistant',
          content: accumulatedContent,
          content_parts: {
            ...(accumulatedReasoning ? { reasoning: accumulatedReasoning, reasoning_length: accumulatedReasoning.length } : {}),
            ...(streamTiming.responseTimeMs != null ? { response_time_ms: streamTiming.responseTimeMs } : {}),
            ...(streamTiming.timeToFirstTokenMs != null ? { time_to_first_token_ms: streamTiming.timeToFirstTokenMs } : {}),
          },
          sequence_num: messages.length + 2, // user msg + this
          branch_id: 0,
          input_tokens: streamUsage.promptTokens ?? null,
          output_tokens: streamUsage.completionTokens ?? null,
          model_ref: null,
          is_error: false,
          error_detail: null,
          parent_message_id: null,
          created_at: new Date().toISOString(),
          // K21-C (D2): attach the accumulated tool calls so the
          // ToolCallIndicator renders from the live stream. null when
          // the turn made no tool calls — keeps the indicator hidden.
          tool_calls: accumulatedToolCalls.length > 0 ? accumulatedToolCalls : null,
          // MCP fan-out (C-ACTIVITY): Tier-A ops streamed this turn → Undo strip.
          activities: accumulatedActivities.length > 0 ? accumulatedActivities : null,
        };
        setMessages((prev) => [...prev, assistantMessage]);
        onStreamEndRef.current?.();

        return accumulatedContent;
      } catch (err) {
        stopThinkingTimer();
        if ((err as Error).name === 'AbortError') {
          setStreamStatus('idle');
          setStreamPhase('idle');
          // Refetch to pick up any partially persisted messages from backend
          void fetchMessages();
          onStreamEndRef.current?.();
          return accumulatedContent;
        }
        setStreamStatus('error');
        setStreamPhase('idle');
        // Refetch on error too — backend may have persisted partial data
        void fetchMessages();
        onStreamEndRef.current?.();
        throw err;
      } finally {
        stopThinkingTimer();
        abortRef.current = null;
        setStreamingText('');
        setStreamingReasoning('');
        setIsComposing(false);  // never leave the drafting indicator stuck on
      }
    },
    [accessToken, sessionId, fetchMessages, editorContext, composeMode, bookContext],
  );

  // ── ARCH-1 C6: resume a suspended run after a frontend-tool decision ──────────
  /** POST the outcome of a frontend tool (the user applied/dismissed a proposed
   *  edit) to the resume endpoint and consume the agent's 2nd pass. Reuses the
   *  full stream consumer via streamPost's override. */
  const submitToolResult = useCallback(
    (runId: string, toolCallId: string, outcome: FrontendToolOutcome, appliedText?: string) => {
      if (!sessionId) return Promise.resolve('');
      return streamPost('', undefined, undefined, {
        url: chatApi.toolResultsUrl(sessionId),
        body: { run_id: runId, tool_call_id: toolCallId, outcome, applied_text: appliedText },
      });
    },
    [sessionId, streamPost],
  );

  // ── MCP fan-out (C-NAV): resume a suspended nav tool with a structured result.
  /** Resolve a `ui_*` navigation tool immediately (no human Apply): the executor
   *  performs the router action, then POSTs the resolve payload (e.g.
   *  `{navigated:true}`) which the agent reads as the tool's result on its next
   *  pass. Distinct from submitToolResult (an outcome-enum gate) because nav
   *  tools resolve with an arbitrary result object, not the apply/confirm enum. */
  const submitToolResolve = useCallback(
    (runId: string, toolCallId: string, result: Record<string, unknown>) => {
      if (!sessionId) return Promise.resolve('');
      return streamPost('', undefined, undefined, {
        url: chatApi.toolResultsUrl(sessionId),
        body: { run_id: runId, tool_call_id: toolCallId, result },
      });
    },
    [sessionId, streamPost],
  );

  // ── Public API ────────────────────────────────────────────────────────────────

  /** Send a new message (normal flow) */
  const send = useCallback(
    (content: string, thinking?: boolean) => {
      // Optimistically add user message to the list
      const optimistic: ChatMessage = {
        message_id: `opt-${Date.now()}`,
        session_id: sessionId ?? '',
        owner_user_id: '',
        role: 'user',
        content,
        content_parts: null,
        sequence_num: messages.length + 1,
        input_tokens: null,
        output_tokens: null,
        model_ref: null,
        is_error: false,
        error_detail: null,
        branch_id: 0,
        parent_message_id: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      return streamPost(content, undefined, thinking);
    },
    [sessionId, messages.length, streamPost],
  );

  /** Edit a user message and re-run from that point */
  const edit = useCallback(
    (content: string, editFromSequence: number) => {
      setMessages((prev) => {
        const truncated = prev.filter((m) => m.sequence_num < editFromSequence);
        const optimistic: ChatMessage = {
          message_id: `edit-${Date.now()}`,
          session_id: sessionId ?? '',
          owner_user_id: '',
          role: 'user',
          content,
          content_parts: null,
          sequence_num: editFromSequence,
          branch_id: 0,
          input_tokens: null,
          output_tokens: null,
          model_ref: null,
          is_error: false,
          error_detail: null,
          parent_message_id: null,
          created_at: new Date().toISOString(),
        };
        return [...truncated, optimistic];
      });
      return streamPost(content, editFromSequence);
    },
    [sessionId, streamPost],
  );

  /** Regenerate the assistant response after a given user message */
  const regenerate = useCallback(
    (userContent: string, userSequenceNum: number) => {
      setMessages((prev) => prev.filter((m) => m.sequence_num <= userSequenceNum));
      return streamPost(userContent, userSequenceNum);
    },
    [streamPost],
  );

  /** Stop the current stream */
  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  /** Refresh messages for a specific branch */
  const refreshBranch = useCallback(
    (branchId: number) => fetchMessages(branchId),
    [fetchMessages],
  );

  return {
    messages,
    isLoading,
    streamingText,
    streamingReasoning,
    streamPhase,
    thinkingElapsed,
    streamStatus,
    isStreaming: streamStatus === 'streaming',
    /** A2A phase-2: composer model is drafting prose this turn. */
    isComposing,
    send,
    edit,
    regenerate,
    stop,
    refresh: fetchMessages,
    refreshBranch,
    /** ARCH-1 C6: resume a suspended run with a frontend-tool outcome. */
    submitToolResult,
    /** MCP fan-out (C-NAV): resolve a suspended `ui_*` nav tool immediately. */
    submitToolResolve,
    /** Set a callback to receive per-token deltas during streaming */
    onStreamDeltaRef,
    /** Set a callback for when streaming ends (success or abort) */
    onStreamEndRef,
    /** K-CLEAN-5 (D-K8-04): set a callback for the per-turn
     *  memory-mode SSE event from chat-service. */
    onMemoryModeRef,
  };
}
