// LOOM Composition (T5.4 M4 Slice B) — the SharedWorker-backed stream client.
//
// Same public shape as useCompositionStream, but the generation runs in the
// SharedWorker (liveState.shared-worker) so the opener and every pop-out share ONE
// stream. This hook just sends commands (start/stop/clear) to the worker port and
// mirrors the snapshots it broadcasts back. Engaged only when `enabled` (windowing on /
// inside a pop-out) AND SharedWorker exists; otherwise LiveStateContext uses the
// in-process hook instead — so this never runs without a real worker.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { GenerateArgs } from './runCompositionGeneration';
import type { LiveStreamState } from '../workers/liveStateHub';

const EMPTY: LiveStreamState = { ghost: '', streaming: false, jobId: null, error: null, reasoning: null };

export function useSharedCompositionStream(token: string | null, enabled: boolean) {
  const [state, setState] = useState<LiveStreamState>(EMPTY);
  const portRef = useRef<MessagePort | null>(null);
  const tokenRef = useRef(token);
  tokenRef.current = token;

  useEffect(() => {
    if (!enabled || typeof SharedWorker === 'undefined') return;
    let worker: SharedWorker;
    try {
      worker = new SharedWorker(new URL('../workers/liveState.shared-worker.ts', import.meta.url), { type: 'module' });
    } catch {
      return; // construction failed → caller stays on the in-process path
    }
    const port = worker.port;
    portRef.current = port;
    port.onmessage = (e: MessageEvent) => {
      if (e.data?.type === 'state') setState(e.data.state as LiveStreamState);
    };
    // No silent seams: if the worker script errors (e.g. failed to load post-deploy),
    // surface it instead of letting Generate hang with no feedback. Best-effort —
    // SharedWorker error delivery to the parent varies by browser; the full
    // ack-timeout degrade is tracked (D-T5.4-POPOUT-WORKER-HEALTHCHECK).
    const onErr = () => setState((s) => ({ ...s, streaming: false, error: 'composition worker failed — reload to retry' }));
    worker.onerror = onErr;
    port.onmessageerror = onErr;
    port.start();
    return () => {
      // On a window navigating away we close our port; on a TAB close no cleanup runs,
      // so the worker (and the run) survives for the other windows — the whole point.
      try { port.close(); } catch { /* already gone */ }
      portRef.current = null;
    };
  }, [enabled]);

  const start = useCallback(async (args: GenerateArgs) => {
    portRef.current?.postMessage({ type: 'start', args, token: tokenRef.current });
  }, []);
  const stop = useCallback(() => { portRef.current?.postMessage({ type: 'stop' }); }, []);
  const clearGhost = useCallback(() => {
    portRef.current?.postMessage({ type: 'clear' });
    setState((s) => ({ ...s, ghost: '' }));   // optimistic; the worker confirms via snapshot
  }, []);

  return { ...state, start, stop, clearGhost };
}
