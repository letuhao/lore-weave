// LOOM Composition (M8) — co-write SSE stream (controller).
//
// Consumes POST /generate's text/event-stream via fetch + ReadableStream (NOT
// EventSource — that's GET-only and can't carry the JWT). Mirrors chat's
// streamPost. The streamed tokens accumulate into a FE-LOCAL `ghost` buffer that
// is NEVER written to the editor doc or autosaved until the author Accepts
// (§13 SC4) — the panel's accept handler reads `ghost`, inserts it, then clears.
import { useCallback, useEffect, useRef, useState } from 'react';
import { compositionApi } from '../api';
import type { StreamEvent } from '../types';

export type GenerateArgs = {
  projectId: string;
  outlineNodeId: string;
  modelSource: string;
  modelRef: string;
  operation?: string;
  guide?: string;
  maxOutputTokens?: number;
  /** "none" disables hidden thinking on reasoning-model drafters so reasoning
   * tokens don't eat the budget (empty ghost). Omit for the model default. */
  reasoningEffort?: 'none' | 'low' | 'medium' | 'high';
};

export function useCompositionStream(token: string | null) {
  const [ghost, setGhost] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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
      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await fetch(compositionApi.generateUrl(args.projectId), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token ?? ''}` },
          body: JSON.stringify({
            outline_node_id: args.outlineNodeId,
            model_source: args.modelSource,
            model_ref: args.modelRef,
            operation: args.operation ?? 'draft_scene',
            guide: args.guide ?? '',
            max_output_tokens: args.maxOutputTokens ?? 800,
            // Omit when unset → server uses the model default.
            ...(args.reasoningEffort ? { reasoning_effort: args.reasoningEffort } : {}),
          }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          setError(`generate failed (${res.status})`);
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? ''; // keep a partial line across chunks
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            let ev: StreamEvent;
            try {
              ev = JSON.parse(line.slice(6));
            } catch {
              continue; // partial/garbled frame — skip
            }
            if (ev.type === 'job') setJobId(ev.job_id);
            else if (ev.type === 'token') setGhost((g) => g + ev.delta);
            else if (ev.type === 'error') setError(ev.error);
          }
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') setError(String(e));
      } finally {
        // Only the CURRENT stream may flip the shared state — a superseded
        // start (its read aborted by a newer Generate) must not clobber the
        // newer controller / streaming flag.
        if (abortRef.current === controller) {
          setStreaming(false);
          abortRef.current = null;
        }
      }
    },
    [token],
  );

  const clearGhost = useCallback(() => setGhost(''), []);
  return { ghost, streaming, jobId, error, start, stop, clearGhost };
}
