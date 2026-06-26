// LOOM Composition (M8) — co-write SSE stream (controller).
//
// Consumes POST /generate's text/event-stream via fetch + ReadableStream (NOT
// EventSource — that's GET-only and can't carry the JWT). The streamed tokens
// accumulate into a FE-LOCAL `ghost` buffer that is NEVER written to the editor doc or
// autosaved until the author Accepts (§13 SC4) — the panel's accept handler reads
// `ghost`, inserts it, then clears.
//
// T5.4 M4 Slice B: the fetch/SSE/job CORE lives in runCompositionGeneration (a pure,
// worker-safe module). This hook drives it in-process and maps its events to state.
// The SharedWorker-backed path (one shared stream across windows) wraps this same core
// and is engaged by LiveStateContext only when windowing is on + SharedWorker exists;
// this hook is the always-correct in-process path (and the degrade fallback).
import { useCallback, useEffect, useRef, useState } from 'react';
import { runCompositionGeneration, type GenerateArgs, type ReasoningInfo } from './runCompositionGeneration';

export type { GenerateArgs } from './runCompositionGeneration';

export function useCompositionStream(token: string | null) {
  const [ghost, setGhost] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // How the server resolved reasoning for this run (for the UI badge).
  const [reasoning, setReasoning] = useState<ReasoningInfo | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  // Abort any in-flight stream on unmount (no ghost leaks, no dangling fetch).
  useEffect(() => () => abortRef.current?.abort(), []);

  const start = useCallback(
    async (args: GenerateArgs) => {
      abortRef.current?.abort(); // a 2nd generate cancels the in-flight one (S2 also BE-side)
      setGhost('');
      setError(null);
      setJobId(null);
      setReasoning(null);
      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      // Only the CURRENT run may flip shared state — a superseded start (its read aborted
      // by a newer Generate) must not clobber the newer controller's ghost/streaming.
      const isCurrent = () => abortRef.current === controller;
      try {
        await runCompositionGeneration(
          args,
          token,
          {
            onJob: (id, r) => { if (!isCurrent()) return; setJobId(id); if (r) setReasoning(r); },
            onToken: (delta) => { if (!isCurrent()) return; setGhost((g) => g + delta); },
            onText: (text) => { if (!isCurrent()) return; setGhost(text); },
            onError: (msg) => { if (!isCurrent()) return; setError(msg); },
          },
          controller.signal,
        );
      } catch (e) {
        if ((e as Error).name !== 'AbortError' && isCurrent()) setError(String(e));
      } finally {
        if (isCurrent()) {
          setStreaming(false);
          abortRef.current = null;
        }
      }
    },
    [token],
  );

  const clearGhost = useCallback(() => setGhost(''), []);
  return { ghost, streaming, jobId, error, reasoning, start, stop, clearGhost };
}
