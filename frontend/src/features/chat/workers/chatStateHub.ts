// L-chat (T5.4 M2 / D-T5.4-CHAT-HOIST) — the SharedWorker's PURE protocol core.
//
// Owns ONE cowriter chat turn and fans its state to every connected window port,
// so the opener and any pop-outs share a single stream (and it survives the
// opener closing — the worker lives as long as ANY window keeps a port).
// Extracted from the worker shell so it's unit-testable without a real
// SharedWorker (jsdom has none). Mirrors composition's `createLiveStateHub`.
//
// Protocol (snapshot-based, not incremental → drift-free): every state change
// broadcasts the FULL snapshot `{type:'state', state}`; a newly-connected port
// gets the current snapshot immediately (late-join replay). Inbound:
// start | stop | clear | toolResult (the resume path re-enters the same run loop
// with an override url/body).
//
// The snapshot is RICH (the whole chat turn surface) so a late-joining pop-out
// reconstructs the in-flight turn from one message: streaming text/reasoning,
// phase + elapsed clock, tool calls, activities, memory mode, the suspended-run
// frontend-tool gate, usage/timing, and the terminal assembled message.
import type {
  ChatCallbacks,
  ChatStreamArgs,
  ChatStreamResult,
  MemoryMode,
  StreamPhase,
} from '../hooks/runChatStream';
import type { ActivityEvent, ToolCallRecord, AgentSurfaceState, ContextBudget, CompactionEvent } from '../types';

export type StreamStatus = 'idle' | 'streaming' | 'error';

/** A suspended frontend-tool run awaiting the user's apply/dismiss. Mirrors the
 *  pendingToolCall the RUN_FINISHED handler records — surfaced on the snapshot so
 *  a late-joining window can render the Apply/Dismiss gate. */
export type SuspendedRun = {
  runId: string;
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
} | null;

export type ChatLiveState = {
  /** Monotonic id, bumped on every `start`. Lets the consumer dedupe the
   *  single-writer onStreamEnd fan-out + the optimistic/assembled append so two
   *  windows don't double-fire. */
  turnId: number;
  streamingText: string;
  streamingReasoning: string;
  streamPhase: StreamPhase;
  thinkingElapsed: number;
  streamStatus: StreamStatus;
  isComposing: boolean;
  toolCalls: ToolCallRecord[];
  activities: ActivityEvent[];
  memoryMode: MemoryMode | null;
  agentSurface: AgentSurfaceState | null;
  /** RAID Wave A3: the last turn-finish context-budget snapshot (header meter).
   *  On the snapshot so it survives dock float/close like the other facets. */
  contextBudget: ContextBudget | null;
  /** W2: the turn's compaction report (null when compaction did no work this
   *  turn). The consumer dedupes the toast per turnId, mirroring memoryMode. */
  compaction: CompactionEvent | null;
  messageId: string | null;
  usage: { promptTokens?: number; completionTokens?: number };
  timing: { responseTimeMs?: number; timeToFirstTokenMs?: number };
  suspendedRun: SuspendedRun;
  /** D-T5.4-CHAT-MULTIWINDOW — the globally-unique nonce of the `start`/`toolResult`
   *  that began this turn (echoed verbatim from the inbound message). The window whose
   *  pending nonce matches owns the turn's terminal side-effects; every other window is
   *  an observer. Nonce (not "the port that sent start") so attribution is race-free even
   *  when two windows start turns in the same tick. Null for the idle/cleared state. */
  initiatorNonce: string | null;
  /** True once the turn finished cleanly (the consumer appends + fires fan-out,
   *  deduped on turnId). Reset to false on the next `start`. */
  ended: boolean;
  /** The assembled assistant turn — present on `ended` so the consumer can append
   *  the final message (it owns sequence_num, so it re-assembles via the hook's
   *  assembleAssistantMessage). */
  result: ChatStreamResult | null;
  error: string | null;
};

export type InboundMessage =
  | { type: 'start'; args: ChatStreamArgs; token: string | null; nonce?: string }
  | { type: 'stop' }
  | { type: 'clear' }
  // The resume / tool-result path: re-enter the run loop with an override
  // url/body (chatApi.toolResultsUrl + the outcome payload). Same stream
  // handling, so a tool result submitted in one window resumes the turn for ALL
  // windows via the broadcast snapshot.
  | { type: 'toolResult'; override: { url: string; body: Record<string, unknown> }; token: string | null; nonce?: string };

export type OutboundMessage = { type: 'state'; state: ChatLiveState };

/** Minimal port shape — a real MessagePort, or a fake in tests. */
export type HubPort = {
  postMessage: (m: OutboundMessage) => void;
  onmessage: ((e: { data: InboundMessage }) => void) | null;
  start?: () => void;
};

type RunFn = (
  args: ChatStreamArgs,
  token: string | null,
  cb: ChatCallbacks,
  signal: AbortSignal,
) => Promise<ChatStreamResult>;

const EMPTY: ChatLiveState = {
  turnId: 0,
  streamingText: '',
  streamingReasoning: '',
  streamPhase: 'idle',
  thinkingElapsed: 0,
  streamStatus: 'idle',
  isComposing: false,
  toolCalls: [],
  activities: [],
  memoryMode: null,
  agentSurface: null,
  contextBudget: null,
  compaction: null,
  messageId: null,
  usage: {},
  timing: {},
  suspendedRun: null,
  initiatorNonce: null,
  ended: false,
  result: null,
  error: null,
};

export function createChatStateHub(run: RunFn) {
  const ports = new Set<HubPort>();
  let state: ChatLiveState = { ...EMPTY };
  let ctrl: AbortController | null = null;
  let thinkingTimer: ReturnType<typeof setInterval> | null = null;
  let thinkingStart = 0;

  const broadcast = () => {
    const msg: OutboundMessage = { type: 'state', state };
    for (const p of ports) {
      try { p.postMessage(msg); } catch { /* dead port (closed window) */ }
    }
  };
  const set = (patch: Partial<ChatLiveState>) => { state = { ...state, ...patch }; broadcast(); };

  const stopThinkingTimer = () => {
    if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
  };
  const startThinkingTimer = () => {
    thinkingStart = Date.now();
    // setInterval exists in a Worker global scope; in tests the hub is driven
    // without a real timer (phase transitions still patch the snapshot).
    thinkingTimer = setInterval(() => { set({ thinkingElapsed: (Date.now() - thinkingStart) / 1000 }); }, 100);
  };

  function beginRun(args: ChatStreamArgs, token: string | null, nonce: string | null) {
    ctrl?.abort();                       // a 2nd turn supersedes the in-flight one
    stopThinkingTimer();
    const c = new AbortController();
    ctrl = c;
    const isCurrent = () => ctrl === c;
    // Fresh turn — bump turnId, stamp the initiator nonce, reset the streaming
    // facets, keep ports. The nonce rides every broadcast of this turn so the
    // initiating window (and only it) claims the terminal side-effects.
    state = {
      ...EMPTY,
      turnId: state.turnId + 1,
      initiatorNonce: nonce,
      streamStatus: 'streaming',
    };
    broadcast();

    const cb: ChatCallbacks = {
      onPhase: (phase) => {
        if (!isCurrent()) return;
        if (phase === 'thinking') { startThinkingTimer(); set({ streamPhase: 'thinking' }); }
        else if (phase === 'responding') { stopThinkingTimer(); set({ streamPhase: 'responding' }); }
      },
      onReasoning: (accumulated) => { if (isCurrent()) set({ streamingReasoning: accumulated }); },
      onText: (accumulated) => { if (isCurrent()) set({ streamingText: accumulated }); },
      onToolCall: (record) => {
        if (!isCurrent()) return;
        // Push onto the live toolCalls array (so the indicator renders mid-turn)
        // and, for a suspended frontend tool, also surface the gate.
        const toolCalls = [...state.toolCalls, record];
        const suspendedRun: SuspendedRun = record.pending
          ? {
              runId: record.runId ?? '',
              toolCallId: record.toolCallId ?? '',
              toolName: record.tool,
              args: (record.args as Record<string, unknown>) ?? {},
            }
          : state.suspendedRun;
        set({ toolCalls, suspendedRun });
      },
      onActivity: (activity) => {
        if (isCurrent()) set({ activities: [...state.activities, activity] });
      },
      onComposing: (active) => { if (isCurrent()) set({ isComposing: active }); },
      onMemoryMode: (mode) => { if (isCurrent()) set({ memoryMode: mode }); },
      onAgentSurface: (payload) => { if (isCurrent()) set({ agentSurface: payload }); },
      onContextBudget: (budget) => { if (isCurrent()) set({ contextBudget: budget }); },
      onCompaction: (event) => { if (isCurrent()) set({ compaction: event }); },
      onAbort: (partial) => {
        if (!isCurrent()) return;
        stopThinkingTimer();
        // Abort mirrors the inline path: idle, no terminal append. The partial's
        // accumulators are already reflected via the per-facet patches above; we
        // just settle the status. (ended stays false → no append/fan-out.)
        set({ streamStatus: 'idle', streamPhase: 'idle', isComposing: false, result: partial });
      },
      onEnd: (result) => {
        if (!isCurrent()) return;
        stopThinkingTimer();
        // Terminal — settle + carry the assembled result so the consumer appends
        // (deduped on turnId) and fires the single-writer fan-out ONCE.
        set({
          streamStatus: 'idle',
          streamPhase: 'idle',
          isComposing: false,
          messageId: result.messageId,
          usage: result.usage,
          timing: result.timing,
          toolCalls: result.toolCalls,
          activities: result.activities,
          result,
          ended: true,
        });
      },
    };

    run(args, token, cb, c.signal)
      .catch((e: unknown) => {
        if (isCurrent() && (e as Error)?.name !== 'AbortError') {
          stopThinkingTimer();
          set({ streamStatus: 'error', streamPhase: 'idle', isComposing: false, error: String((e as Error)?.message ?? e) });
        }
      })
      .finally(() => { if (isCurrent()) ctrl = null; });
  }

  function handle(msg: InboundMessage) {
    if (msg.type === 'start') beginRun(msg.args, msg.token, msg.nonce ?? null);
    else if (msg.type === 'toolResult') beginRun({ sessionId: '', content: '', override: msg.override }, msg.token, msg.nonce ?? null);
    else if (msg.type === 'stop') {
      ctrl?.abort();
      ctrl = null;
      stopThinkingTimer();
      set({ streamStatus: 'idle', streamPhase: 'idle', isComposing: false });
    } else if (msg.type === 'clear') {
      set({ streamingText: '', streamingReasoning: '', toolCalls: [], activities: [], suspendedRun: null, ended: false, result: null, error: null });
    }
  }

  function addPort(port: HubPort) {
    ports.add(port);
    port.onmessage = (e) => handle(e.data);
    port.start?.();
    port.postMessage({ type: 'state', state });   // late-join replay
  }

  return {
    addPort,
    /** test/inspection helpers */
    _state: () => state,
    _portCount: () => ports.size,
    _handle: handle,
  };
}
