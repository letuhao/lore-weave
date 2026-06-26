// L-chat (T5.4 M2 / D-T5.4-CHAT-HOIST) — the SharedWorker-backed chat stream client.
//
// Same snapshot shape as the in-process path, but the chat turn runs in the
// SharedWorker (chatLiveState.shared-worker) so the opener and every pop-out
// share ONE turn. This hook just sends commands (start/stop/clear/toolResult) to
// the worker port and mirrors the snapshots it broadcasts back. Engaged only
// when `enabled` (chat windowing on / inside a pop-out) AND SharedWorker exists;
// otherwise ChatLiveStateProvider keeps the in-process hook — so this never runs
// without a real worker. Mirrors composition's `useSharedCompositionStream`.
import { useCallback, useEffect, useRef, useState } from 'react';
import { chatApi } from '../api';
import type { ChatStreamArgs } from './runChatStream';
import type { FrontendToolOutcome } from './useChatMessages';
import type { ChatLiveState } from '../workers/chatStateHub';

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
  messageId: null,
  usage: {},
  timing: {},
  suspendedRun: null,
  ended: false,
  result: null,
  error: null,
};

// WS-D (D-T5.4-POPOUT-WORKER-HEALTHCHECK) — the hub replays a snapshot to every
// new port the instant it connects (chatStateHub.addPort → postMessage). So a
// healthy worker ALWAYS sends a message within a few ms of `port.start()`. If
// none arrives within this window the worker script failed to load / is wedged →
// degrade with a clear error instead of letting Send hang silently.
const ACK_TIMEOUT_MS = 4000;

export function useSharedChatStream(token: string | null, enabled: boolean) {
  const [state, setState] = useState<ChatLiveState>(EMPTY);
  const portRef = useRef<MessagePort | null>(null);
  // Token is held in a ref so a refresh mid-stream plumbs the NEW bearer to the
  // worker on the next start/toolResult without re-subscribing the port (a long
  // turn already in flight keeps the token it started with — the worker holds it).
  const tokenRef = useRef(token);
  tokenRef.current = token;

  useEffect(() => {
    if (!enabled || typeof SharedWorker === 'undefined') return;
    let worker: SharedWorker;
    try {
      worker = new SharedWorker(new URL('../workers/chatLiveState.shared-worker.ts', import.meta.url), { type: 'module' });
    } catch {
      return; // construction failed → caller stays on the in-process path
    }
    const port = worker.port;
    portRef.current = port;
    // Ack-timeout health check: arm a timer; the hub's connect-replay should
    // clear it almost immediately. If it fires, the worker is unresponsive → degrade.
    let acked = false;
    const ackTimer = setTimeout(() => {
      if (acked) return;
      setState((s) => ({ ...s, streamStatus: 'error', error: 'chat worker not responding — reload to retry' }));
    }, ACK_TIMEOUT_MS);
    port.onmessage = (e: MessageEvent) => {
      acked = true;
      clearTimeout(ackTimer);   // any message proves the worker is alive
      if (e.data?.type === 'state') setState(e.data.state as ChatLiveState);
    };
    // No silent seams: if the worker script errors (e.g. failed to load
    // post-deploy), surface it instead of letting Send hang with no feedback.
    const onErr = () => {
      acked = true;
      clearTimeout(ackTimer);
      setState((s) => ({ ...s, streamStatus: 'error', error: 'chat worker failed — reload to retry' }));
    };
    worker.onerror = onErr;
    port.onmessageerror = onErr;
    port.start();
    return () => {
      clearTimeout(ackTimer);
      // On a window navigating away we close our port; on a TAB close no cleanup
      // runs, so the worker (and the turn) survives for the other windows — the
      // whole point.
      try { port.close(); } catch { /* already gone */ }
      portRef.current = null;
    };
  }, [enabled]);

  const start = useCallback((args: ChatStreamArgs) => {
    portRef.current?.postMessage({ type: 'start', args, token: tokenRef.current });
  }, []);
  const stop = useCallback(() => { portRef.current?.postMessage({ type: 'stop' }); }, []);
  const clear = useCallback(() => {
    portRef.current?.postMessage({ type: 'clear' });
    setState((s) => ({ ...s, streamingText: '', streamingReasoning: '', toolCalls: [], activities: [], suspendedRun: null, ended: false, result: null }));
  }, []);

  // ARCH-1 C6: resume a suspended run after a frontend-tool decision. Builds the
  // same override url/body the inline hook does, then re-enters the worker's run
  // loop — so other windows see the resumed turn via the broadcast snapshot.
  const submitToolResult = useCallback(
    (sessionId: string, runId: string, toolCallId: string, outcome: FrontendToolOutcome, appliedText?: string) => {
      portRef.current?.postMessage({
        type: 'toolResult',
        override: {
          url: chatApi.toolResultsUrl(sessionId),
          body: { run_id: runId, tool_call_id: toolCallId, outcome, applied_text: appliedText },
        },
        token: tokenRef.current,
      });
    },
    [],
  );

  // MCP fan-out (C-NAV): resolve a `ui_*` nav tool immediately with a structured result.
  const submitToolResolve = useCallback(
    (sessionId: string, runId: string, toolCallId: string, result: Record<string, unknown>) => {
      portRef.current?.postMessage({
        type: 'toolResult',
        override: {
          url: chatApi.toolResultsUrl(sessionId),
          body: { run_id: runId, tool_call_id: toolCallId, result },
        },
        token: tokenRef.current,
      });
    },
    [],
  );

  return { ...state, start, stop, clear, submitToolResult, submitToolResolve };
}
