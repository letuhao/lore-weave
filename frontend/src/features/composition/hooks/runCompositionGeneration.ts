// LOOM Composition (T5.4 M4 Slice B) — the PURE co-writer generation core.
//
// Extracted from useCompositionStream so the SAME fetch / SSE-parse / 202-job-poll
// logic runs in BOTH places without divergence:
//   • in-process (the hook's degrade path — default, byte-identical to pre-Slice-B),
//   • inside the SharedWorker (liveState.shared-worker), which owns ONE stream and
//     fans these same events to every window's port (survives the opener closing).
// No React, no DOM — safe to import in a worker. `apiBase()` is '' (relative), which a
// worker resolves against its own same-origin script URL, so the gateway proxy path is
// identical to the main thread.
import { compositionApi } from '../api';
import type { StreamEvent } from '../types';

export type GenerateArgs = {
  projectId: string;
  outlineNodeId?: string;
  modelSource: string;
  modelRef: string;
  operation?: string;
  guide?: string;
  maxOutputTokens?: number;
  selection?: string;
  sceneContext?: string | null;
  reasoning?: 'off' | 'auto' | 'low' | 'medium' | 'high';
  modelKind?: string;
  modelName?: string;
};

export type ReasoningInfo = { source: string; effort: string | null };

/** Event sink — the hook maps these to setState; the worker fans them to all ports. */
export type GenerationCallbacks = {
  onJob?: (jobId: string, reasoning?: ReasoningInfo) => void;
  onToken?: (delta: string) => void;   // append to ghost (streaming)
  onText?: (text: string) => void;     // SET ghost (the 202-batch job result)
  onError?: (message: string) => void;
};

function buildRequest(args: GenerateArgs): { url: string; body: Record<string, unknown> } {
  // A `selection` switches to the selection-edit endpoint (scene-decoupled); otherwise
  // this is the scene-draft generate. The SSE handling is shared.
  const isSelection = args.selection != null;
  const url = isSelection
    ? compositionApi.selectionEditUrl(args.projectId)
    : compositionApi.generateUrl(args.projectId);
  const body = isSelection
    ? {
        operation: args.operation ?? 'rewrite',
        selection: args.selection,
        scene_context: args.sceneContext ?? null,
        model_source: args.modelSource,
        model_ref: args.modelRef,
        guide: args.guide ?? '',
        max_output_tokens: args.maxOutputTokens ?? 1024,
        reasoning: args.reasoning ?? 'auto',
        ...(args.modelKind ? { model_kind: args.modelKind } : {}),
        ...(args.modelName ? { model_name: args.modelName } : {}),
      }
    : {
        outline_node_id: args.outlineNodeId,
        model_source: args.modelSource,
        model_ref: args.modelRef,
        operation: args.operation ?? 'draft_scene',
        guide: args.guide ?? '',
        max_output_tokens: args.maxOutputTokens ?? 800,
        reasoning: args.reasoning ?? 'auto',
        ...(args.modelKind ? { model_kind: args.modelKind } : {}),
        ...(args.modelName ? { model_name: args.modelName } : {}),
      };
  return { url, body };
}

/** Run one generation: POST → either a 202 batch job (poll to terminal) or an SSE token
 *  stream. Emits via `cb`; resolves when the run finishes (or aborts via `signal`).
 *  Throws only on a non-AbortError fetch failure (the caller maps that to onError). */
export async function runCompositionGeneration(
  args: GenerateArgs, token: string | null, cb: GenerationCallbacks, signal: AbortSignal,
): Promise<void> {
  const { url, body } = buildRequest(args);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token ?? ''}` },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) { cb.onError?.(`generate failed (${res.status})`); return; }

  // M4: with the batch worker on, selection-edit answers 202 application/json
  // `{ job_id, status:'pending' }` instead of SSE. Poll the job to terminal and surface
  // the result text as the ghost (same accept flow as a stream).
  const ctype = res.headers?.get?.('content-type') ?? '';
  if (ctype.includes('application/json')) {
    const accepted = (await res.json()) as { job_id?: string; status?: string };
    if (accepted.job_id) cb.onJob?.(accepted.job_id);
    if (accepted.job_id && (accepted.status === 'pending' || accepted.status === 'running')) {
      const job = await compositionApi.awaitJob(accepted.job_id, token ?? '', signal);
      if (signal.aborted) return; // superseded — don't clobber
      if (job.status === 'failed') {
        cb.onError?.((job.result as { error?: string } | null)?.error ?? 'edit failed');
      } else if (job.status === 'completed') {
        cb.onText?.((job.result as { text?: string } | null)?.text ?? '');
      } else {
        cb.onError?.('edit did not complete in time');
      }
    }
    return;
  }

  if (!res.body) { cb.onError?.(`generate failed (${res.status})`); return; }
  const reader = res.body.getReader();
  // Explicitly cancel the reader when the run is superseded / stopped / unmounted (all
  // abort `signal`). We must NOT rely solely on abort propagating through fetch: if the
  // runtime (or a mocked fetch) doesn't propagate it, the pending read() never resolves
  // and the iteration leaks forever. Cancelling resolves read() with {done:true}.
  const cancelReader = () => void reader.cancel().catch(() => {});
  if (signal.aborted) cancelReader();
  else signal.addEventListener('abort', cancelReader, { once: true });
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
      if (ev.type === 'job') {
        cb.onJob?.(ev.job_id, ev.reasoning_source ? { source: ev.reasoning_source, effort: ev.reasoning_effort ?? null } : undefined);
      } else if (ev.type === 'token') {
        cb.onToken?.(ev.delta);
      } else if (ev.type === 'error') {
        cb.onError?.(ev.error);
      }
    }
  }
}
