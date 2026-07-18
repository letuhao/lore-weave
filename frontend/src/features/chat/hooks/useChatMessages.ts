import { useCallback, useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ChatMessage, AgentSurfaceState, ContextBudget, CompactionEvent } from '../types';
import { runChatStream, assembleAssistantMessage } from './runChatStream';
import type { ChatStreamArgs, StreamPhase, ReasoningEffortLevel } from './runChatStream';
import type { StreamPins } from './useContextRack';
import { useChatLiveStateOptional } from '../providers/ChatLiveStateContext';

type StreamStatus = 'idle' | 'streaming' | 'error';

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
  // H-J / H14 re-price-on-execute: the priced confirm route returned 409
  // reprice_required (actual cost drifted up past the BE threshold). The token is
  // single-use + now spent — the agent must re-propose at the new price, never
  // silently overspend. Distinct from token_expired so the model knows it's a cost
  // change, not a stale token.
  | 'reprice_required'
  | 'action_error'
  | 'cancelled'
  // RAID C2 (DR-C2 §4) — the tool_approval card (Write-mode Tier-A prompt-once):
  // approved_once executes; approved_always also persists the per-user allowlist
  // row; denied feeds "denied by user" so the agent self-corrects.
  | 'approved_once'
  | 'approved_always'
  | 'denied'
  // D3 (PO sign-off) — "Never allow" ON THE CARD: persists a standing DENY for this
  // tool (mirrors approved_always's persist) AND feeds "denied by user" (executes
  // nothing). The natural moment to refuse a tool forever is when it is asking.
  | 'denied_always';

// RAID C2 — HITL permission mode. Persisted per-device in localStorage
// (mirrors the editor's lw_editor_compose_mode pattern): a UI preference,
// sent per-request as `permission_mode` on the message POST.
// RAID B2 (07S §5b) — 'plan': the ask (read-only) surface PLUS the PlanForge
// plan_* tools — research + plan, no prose until the user switches to Write.
export type PermissionMode = 'ask' | 'plan' | 'write';
const PERMISSION_MODE_KEY = 'lw_chat_permission_mode';

function loadPermissionMode(): PermissionMode {
  try {
    const stored = localStorage.getItem(PERMISSION_MODE_KEY);
    return stored === 'ask' || stored === 'plan' ? stored : 'write';
  } catch {
    return 'write';
  }
}

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
  /** S6: the user's per-book display language (set only when showing a
   *  translation). Forwarded so knowledge-service composes entity aliases in
   *  this language for the chat context. Omitted → source-language aliases. */
  displayLanguage?: string,
  enabledTools?: string[],
  enabledSkills?: string[],
  streamPinsRef?: MutableRefObject<StreamPins>,
  /** #09 Lane A: present in the Writing Studio compose panel — enables the studio
   *  dock-nav frontend tools (open panel / focus manuscript unit). */
  studioContext?: { book_id?: string; project_id?: string; active_chapter_id?: string; active_panel_ids?: string[]; context_revision?: number },
) {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  // RAID C2 — Ask/Write permission mode (lazy-init from localStorage, setter
  // writes through — mirrors the editor's composeMode persistence).
  const [permissionMode, setPermissionModeState] = useState<PermissionMode>(loadPermissionMode);
  const setPermissionMode = useCallback((mode: PermissionMode) => {
    setPermissionModeState(mode);
    try { localStorage.setItem(PERMISSION_MODE_KEY, mode); } catch { /* ignore */ }
  }, []);
  const [streamingText, setStreamingText] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [streamPhase, setStreamPhase] = useState<StreamPhase>('idle');
  const [thinkingElapsed, setThinkingElapsed] = useState(0);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle');
  // A2A phase-2: true while the in-turn composer model is drafting prose
  // (compose_prose). Drives a transient "✍️ Drafting…" indicator.
  const [isComposing, setIsComposing] = useState(false);
  // RAID Wave A3: the last turn-finish context-budget snapshot (chat header
  // meter). Local state (not persisted server-side); mirrored from the worker
  // snapshot on the windowing path so it survives dock float/close.
  const [contextBudget, setContextBudget] = useState<ContextBudget | null>(null);
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
  const onAgentSurfaceRef = useRef<((state: AgentSurfaceState) => void) | null>(null);
  /** W2: settable callback for the per-turn `compaction` CUSTOM frame —
   *  ChatStreamProvider registers a toast here ("earlier turns compacted"). */
  const onCompactionRef = useRef<((event: CompactionEvent) => void) | null>(null);

  const resolveStreamPins = useCallback((): StreamPins => {
    const fromRef = streamPinsRef?.current;
    if (fromRef?.enabledTools?.length || fromRef?.enabledSkills?.length) {
      return fromRef;
    }
    return {
      enabledTools: enabledTools?.length ? enabledTools : undefined,
      enabledSkills: enabledSkills?.length ? enabledSkills : undefined,
    };
  }, [streamPinsRef, enabledTools, enabledSkills]);

  // M2 (D-T5.4-CHAT-HOIST): when chat windowing is on AND the browser has
  // SharedWorker, ChatLiveStateProvider owns the turn in the worker and exposes
  // its snapshot here. Default (no provider, or flag off) → `useWorker` is false
  // and this hook owns the in-process stream exactly as before (byte-identical).
  const live = useChatLiveStateOptional();
  const useWorker = live?.useWorker ?? false;
  const worker = live?.shared;
  // Dedupe the per-turn terminal side-effects (clean-end append, abort/error
  // refetch, and the onStreamEnd fan-out) on the worker's monotonic turnId so a
  // single window fires each once. (Cross-window single-firing of onStreamEnd is a
  // separate concern handled at the M2 browser-smoke finalize — D-T5.4-CHAT-MULTIWINDOW.)
  const lastTerminalTurnRef = useRef(0);
  const lastMemoryModeTurnRef = useRef(0);
  // W2: compaction fires at most once per turn; the snapshot rebroadcasts many
  // times, so the toast is deduped on turnId exactly like memoryMode.
  const lastCompactionTurnRef = useRef(0);
  // Replay guard: a late-joining tab receives the hub's addPort FULL-STATE
  // replay, which can carry a PAST turn's compaction — that must seed the
  // dedupe ref silently, never toast. False until this window has seen its
  // first worker snapshot.
  const compactionSeededRef = useRef(false);

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

  // ── Seed the header context meter on session load ─────────────────────────────
  // `contextBudget` was live-only (set from the per-turn SSE `contextBudget`
  // event), so the meter rendered nothing on load/switch/reload until the NEXT
  // turn finished — the "sometimes shows, sometimes not" gap. Clear any stale
  // budget from the previous session, then seed from the LAST turn's persisted
  // frame. Race-safe: only apply if the session hasn't changed AND no live event
  // has already set a (fresher) budget this turn (`prev ?? seed`).
  useEffect(() => {
    setContextBudget(null);
    if (!accessToken || !sessionId) return;
    let ignore = false;
    void chatApi
      .getLatestContextBudget(accessToken, sessionId)
      .then((res) => {
        if (ignore || !res.budget) return;
        setContextBudget((prev) => prev ?? res.budget);
      })
      .catch(() => {
        /* meter simply stays hidden until the next live turn — non-fatal */
      });
    return () => {
      ignore = true;
    };
  }, [accessToken, sessionId]);

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
      // W4: granular effort from the input-bar dropdown (today only 'deep'
      // rides the wire — Fast/Standard stay on the `thinking` boolean).
      reasoningEffort?: ReasoningEffortLevel,
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

      // Thinking timer — driven by phase transitions emitted from runChatStream.
      // (The pure core is timer-free; the elapsed clock + setState live here.)
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

      // M2 (D-T5.4-CHAT-HOIST): the AG-UI parse + accumulator switch moved to the
      // pure, React-free `runChatStream` core (shared verbatim with the
      // SharedWorker path). This hook now just maps the emitted facets onto
      // setState + the settable refs — every observable behavior is preserved.
      let aborted = false;
      try {
        const pins = resolveStreamPins();
        const result = await runChatStream(
          {
            sessionId,
            content,
            ...(editFromSequence != null ? { editFromSequence } : {}),
            ...(thinking != null ? { thinking } : {}),
            ...(reasoningEffort != null ? { reasoningEffort } : {}),
            ...(editorContext ? { editorContext } : {}),
            ...(studioContext ? { studioContext } : {}),
            ...(composeMode != null ? { composeMode } : {}),
            ...(bookContext ? { bookContext } : {}),
            ...(displayLanguage ? { displayLanguage } : {}),
            ...(pins.enabledTools?.length ? { enabledTools: pins.enabledTools } : {}),
            ...(pins.enabledSkills?.length ? { enabledSkills: pins.enabledSkills } : {}),
            permissionMode,
            ...(override ? { override } : {}),
          },
          accessToken,
          {
            onPhase: (phase) => {
              if (phase === 'thinking') {
                // First reasoning delta → start the elapsed timer.
                setStreamPhase('thinking');
                startThinkingTimer();
              } else if (phase === 'responding') {
                // First text delta → stop the timer (no-op if never started).
                stopThinkingTimer();
                setStreamPhase('responding');
              }
            },
            onReasoning: (accumulated, delta) => {
              setStreamingReasoning(accumulated);
              onStreamDeltaRef.current?.(delta, 'reasoning');
            },
            onText: (accumulated, delta) => {
              setStreamingText(accumulated);
              onStreamDeltaRef.current?.(delta, 'content');
            },
            onComposing: (active) => setIsComposing(active),
            onMemoryMode: (mode) => onMemoryModeRef.current?.(mode),
            onAgentSurface: (payload) => onAgentSurfaceRef.current?.(payload),
            onContextBudget: (budget) => setContextBudget(budget),
            onCompaction: (event) => onCompactionRef.current?.(event),
            onAbort: () => { aborted = true; },
            // onToolCall / onActivity accumulate inside runChatStream and arrive
            // on the terminal result; nothing extra to mirror per-event here.
          },
          controller.signal,
        );

        stopThinkingTimer();

        if (aborted || controller.signal.aborted) {
          // Abort path — the core resolved with the partial. Mirror the legacy
          // AbortError branch: idle, refetch partial-persisted, fire stream-end,
          // return the partial content (do NOT append a synthetic message).
          setStreamStatus('idle');
          setStreamPhase('idle');
          void fetchMessages();
          onStreamEndRef.current?.();
          return result.content;
        }

        setStreamStatus('idle');
        setStreamPhase('idle');

        // Seamless append: add the completed assistant message without a refetch.
        const assistantMessage = assembleAssistantMessage(
          result,
          sessionId ?? '',
          messages.length + 2, // user msg + this
        );
        setMessages((prev) => [...prev, assistantMessage]);
        onStreamEndRef.current?.();

        return result.content;
      } catch (err) {
        stopThinkingTimer();
        // runChatStream resolves (not throws) on abort, so a thrown error here is
        // a real RUN_ERROR / non-OK response / network failure.
        setStreamStatus('error');
        setStreamPhase('idle');
        // Refetch on error — backend may have persisted partial data.
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
    [accessToken, sessionId, fetchMessages, editorContext, studioContext, composeMode, bookContext, displayLanguage, resolveStreamPins, messages.length, permissionMode],
  );

  // ── ARCH-1 C6: resume a suspended run after a frontend-tool decision ──────────
  /** POST the outcome of a frontend tool (the user applied/dismissed a proposed
   *  edit) to the resume endpoint and consume the agent's 2nd pass. Reuses the
   *  full stream consumer via streamPost's override. */
  const submitToolResult = useCallback(
    (runId: string, toolCallId: string, outcome: FrontendToolOutcome, appliedText?: string) => {
      if (!sessionId) return Promise.resolve('');
      // Worker path: route the resume through the worker so other windows see the
      // resumed turn via the broadcast snapshot.
      if (useWorker && worker) { worker.submitToolResult(sessionId, runId, toolCallId, outcome, appliedText); return Promise.resolve(''); }
      return streamPost('', undefined, undefined, {
        url: chatApi.toolResultsUrl(sessionId),
        body: { run_id: runId, tool_call_id: toolCallId, outcome, applied_text: appliedText },
      });
    },
    [sessionId, streamPost, useWorker, worker],
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
      if (useWorker && worker) { worker.submitToolResolve(sessionId, runId, toolCallId, result); return Promise.resolve(''); }
      return streamPost('', undefined, undefined, {
        url: chatApi.toolResultsUrl(sessionId),
        body: { run_id: runId, tool_call_id: toolCallId, result },
      });
    },
    [sessionId, streamPost, useWorker, worker],
  );

  // ── M2 worker bridge ──────────────────────────────────────────────────────────
  // When the SharedWorker owns the turn, mirror its broadcast snapshot into this
  // hook's local state so every consumer (mid-stream indicators, the message
  // list) renders identically to the in-process path. Two dedup scopes apply:
  //   • per-WINDOW (lastTerminalTurnRef): the snapshot re-renders many times per
  //     turn; the terminal branch must run once per turn IN THIS window.
  //   • cross-WINDOW (D-T5.4-CHAT-MULTIWINDOW): the hub fans the SAME snapshot to
  //     every window, so the onStreamEnd fan-out + the seamless assembled-append
  //     run ONLY in the window that initiated the turn (worker.initiatedTurnId).
  //     Observer windows (incl. a mid-turn pop-out) converge via refetch instead,
  //     so they pick up both the user message they never optimistically appended
  //     and the assistant turn — without double-firing the fan-out.
  // Inert when !useWorker (default).
  useEffect(() => {
    if (!useWorker || !worker) return;
    // Mirror streaming facets every snapshot (the worker is the source of truth).
    setStreamingText(worker.streamingText);
    setStreamingReasoning(worker.streamingReasoning);
    setStreamPhase(worker.streamPhase);
    setThinkingElapsed(worker.thinkingElapsed);
    setStreamStatus(worker.streamStatus);
    setIsComposing(worker.isComposing);

    // memoryMode: fire once per turn it changed in (dedupe on turnId).
    if (worker.memoryMode && worker.turnId !== lastMemoryModeTurnRef.current) {
      lastMemoryModeTurnRef.current = worker.turnId;
      onMemoryModeRef.current?.(worker.memoryMode);
    }
    if (worker.agentSurface) {
      onAgentSurfaceRef.current?.(worker.agentSurface);
    }
    // RAID Wave A3: mirror the worker's context-budget snapshot (source of truth
    // on the windowing path) into local state so the header meter renders identically.
    if (worker.contextBudget) {
      setContextBudget(worker.contextBudget);
    }
    // W2: compaction toast — fire once per turn it occurred in (dedupe on turnId,
    // mirroring memoryMode; the snapshot rebroadcasts many times per turn).
    // Replay guard: the FIRST snapshot after mount (the hub's full-state replay
    // to a late-joining tab) and any non-streaming snapshot only RECORD the
    // compaction's turnId — a stale compaction must not toast again. Only a
    // turnId change observed while a stream is live is a fresh compaction.
    if (worker.compaction && worker.turnId !== lastCompactionTurnRef.current) {
      const isReplay = !compactionSeededRef.current || worker.streamStatus !== 'streaming';
      lastCompactionTurnRef.current = worker.turnId;
      if (!isReplay) onCompactionRef.current?.(worker.compaction);
    }
    compactionSeededRef.current = true;

    // Terminal handling — ONCE per turn per window, deduped on the worker's turnId.
    // Two facets, with DIFFERENT scoping:
    //   • message list (writer-scoped): the INITIATOR appends the assembled assistant
    //     message seamlessly (its optimistic user msg is already local); every other
    //     window — and any abort/error — converges by refetch (server is SSOT).
    //   • onStreamEnd fan-out (per-WINDOW): session-list refresh + pending-facts
    //     refetch are idempotent reads of THIS window's own derived state, so EVERY
    //     window must fire them — both to keep an observer's sidebar/facts fresh AND
    //     so the turn is never left untracked if the initiator window closed mid-turn
    //     (D-T5.4-CHAT-MULTIWINDOW-ORPHAN). N× idempotent GETs is the (small) cost of
    //     never orphaning; refreshSessions is itself debounced.
    const cleanEnd = worker.ended && !!worker.result;
    const nonCleanTerminal =
      worker.streamStatus === 'error' ||
      (worker.streamStatus === 'idle' && !worker.ended && worker.result != null);
    // This window appended the optimistic user msg iff it initiated the turn.
    const isWriter = worker.turnId > 0 && worker.turnId === worker.initiatedTurnId;
    if ((cleanEnd || nonCleanTerminal) && worker.turnId > 0 && worker.turnId !== lastTerminalTurnRef.current) {
      lastTerminalTurnRef.current = worker.turnId;
      if (cleanEnd && isWriter) {
        // Writer (initiator) → seamless append. Its optimistic user message is
        // already in `messages`, so derive sequence_num from the freshest list
        // (functional update; review-impl off-by-one: the fixed length+2 offset
        // double-counted the optimistic user msg). Last seq + 1 is path-agnostic.
        const result = worker.result!;
        setMessages((prev) => {
          const lastSeq = prev.length ? prev[prev.length - 1].sequence_num : 0;
          return [...prev, assembleAssistantMessage(result, sessionId ?? '', lastSeq + 1)];
        });
        // Clear the streaming buffers (the in-process finally did this).
        setStreamingText('');
        setStreamingReasoning('');
      } else {
        // Observer window (never optimistically appended the user msg), OR
        // abort/error in any window → converge from the server, which is the SSOT
        // for both the user turn and the assistant (partial or assembled).
        void fetchMessages();
      }
      // Per-window (NOT writer-gated): each window refreshes its OWN session list +
      // pending facts. This is what makes the orphan a non-event — a surviving
      // observer keeps the session tracked + resumable even if the initiator is gone.
      onStreamEndRef.current?.();
    }
    // worker is a fresh object each render (spread snapshot); gate on the fields
    // that actually drive the mirror to avoid an unnecessary re-run storm.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    useWorker, worker?.turnId, worker?.initiatedTurnId, worker?.streamingText, worker?.streamingReasoning,
    worker?.streamPhase, worker?.thinkingElapsed, worker?.streamStatus, worker?.isComposing,
    worker?.memoryMode, worker?.contextBudget, worker?.compaction, worker?.ended, sessionId,
  ]);

  /** Build the per-turn ChatStreamArgs (worker path) from the hook's props. */
  const buildArgs = useCallback(
    (content: string, editFromSequence?: number, thinking?: boolean, reasoningEffort?: ReasoningEffortLevel): ChatStreamArgs => {
      const pins = resolveStreamPins();
      return {
        sessionId: sessionId ?? '',
        content,
        ...(editFromSequence != null ? { editFromSequence } : {}),
        ...(thinking != null ? { thinking } : {}),
        ...(reasoningEffort != null ? { reasoningEffort } : {}),
        ...(editorContext ? { editorContext } : {}),
        ...(studioContext ? { studioContext } : {}),
        ...(composeMode != null ? { composeMode } : {}),
        ...(bookContext ? { bookContext } : {}),
        ...(displayLanguage ? { displayLanguage } : {}),
        ...(pins.enabledTools?.length ? { enabledTools: pins.enabledTools } : {}),
        ...(pins.enabledSkills?.length ? { enabledSkills: pins.enabledSkills } : {}),
        permissionMode,
      };
    },
    [sessionId, editorContext, studioContext, composeMode, bookContext, displayLanguage, resolveStreamPins, permissionMode],
  );

  // ── Public API ────────────────────────────────────────────────────────────────

  /** Send a new message (normal flow). `reasoningEffort` (W4) is the granular
   *  effort from the input-bar dropdown — only 'deep' rides the wire today. */
  const send = useCallback(
    (content: string, thinking?: boolean, reasoningEffort?: ReasoningEffortLevel) => {
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
      // Optimistic user-message append stays main-thread (it's not stream state).
      setMessages((prev) => [...prev, optimistic]);
      // Worker path: hand the turn to the SharedWorker (returns void; the
      // assembled assistant message arrives via the snapshot bridge). Inline
      // path: own the stream as before.
      if (useWorker && worker) { worker.start(buildArgs(content, undefined, thinking, reasoningEffort)); return Promise.resolve(''); }
      return streamPost(content, undefined, thinking, undefined, reasoningEffort);
    },
    [sessionId, messages.length, streamPost, useWorker, worker, buildArgs],
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
      if (useWorker && worker) { worker.start(buildArgs(content, editFromSequence)); return Promise.resolve(''); }
      return streamPost(content, editFromSequence);
    },
    [sessionId, streamPost, useWorker, worker, buildArgs],
  );

  /** Regenerate the assistant response after a given user message */
  const regenerate = useCallback(
    (userContent: string, userSequenceNum: number) => {
      setMessages((prev) => prev.filter((m) => m.sequence_num <= userSequenceNum));
      if (useWorker && worker) { worker.start(buildArgs(userContent, userSequenceNum)); return Promise.resolve(''); }
      return streamPost(userContent, userSequenceNum);
    },
    [streamPost, useWorker, worker, buildArgs],
  );

  /** Stop the current stream */
  const stop = useCallback(() => {
    // Abort propagation — stop from any window aborts the worker's single
    // controller, so all windows see the stop via the snapshot.
    if (useWorker && worker) { worker.stop(); return; }
    abortRef.current?.abort();
  }, [useWorker, worker]);

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
    /** RAID Wave A3: last turn-finish context-budget snapshot (header meter). */
    contextBudget,
    /** RAID C2: HITL permission mode (ask|write) + persisted setter. */
    permissionMode,
    setPermissionMode,
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
    onAgentSurfaceRef,
    /** W2: set a callback for the per-turn `compaction` CUSTOM frame. */
    onCompactionRef,
  };
}
