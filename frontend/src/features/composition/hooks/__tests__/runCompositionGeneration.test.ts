import { afterEach, describe, expect, it, vi } from 'vitest';
import { runCompositionGeneration, type GenerationCallbacks } from '../runCompositionGeneration';

// The core imports compositionApi for url builders + awaitJob — mock them so the test
// drives only the fetch/SSE/job-poll logic.
vi.mock('../../api', () => ({
  compositionApi: {
    generateUrl: (p: string) => `/v1/works/${p}/generate`,
    selectionEditUrl: (p: string) => `/v1/works/${p}/selection-edit`,
    awaitJob: vi.fn(),
  },
}));
import { compositionApi } from '../../api';

afterEach(() => vi.restoreAllMocks());

function sink() {
  const calls = { job: [] as unknown[], token: [] as string[], text: [] as string[], error: [] as string[] };
  const cb: GenerationCallbacks = {
    onJob: (id, r) => calls.job.push([id, r]),
    onToken: (d) => calls.token.push(d),
    onText: (t) => calls.text.push(t),
    onError: (m) => calls.error.push(m),
  };
  return { cb, calls };
}

/** A fake streaming Response whose body yields the given SSE text in chunks. */
function streamResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  let i = 0;
  const reader = {
    read: async () => (i < chunks.length ? { done: false, value: enc.encode(chunks[i++]) } : { done: true, value: undefined }),
    cancel: async () => {},
  };
  return {
    ok: true,
    headers: { get: () => 'text/event-stream' },
    body: { getReader: () => reader },
  } as unknown as Response;
}

const ARGS = { projectId: 'p1', outlineNodeId: 'n1', modelSource: 'user_model', modelRef: 'm1' };

describe('runCompositionGeneration (T5.4 M4 Slice B core)', () => {
  it('parses an SSE stream into job + token + error events', async () => {
    const frames = [
      'data: {"type":"job","job_id":"j1","created":true,"grounding_available":false,"reasoning_source":"auto","reasoning_effort":"medium"}\n',
      'data: {"type":"token","delta":"Hello "}\n',
      'data: {"type":"token","delta":"world"}\n',
      'data: {"type":"error","error":"boom"}\n',
    ];
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(frames));
    const { cb, calls } = sink();
    await runCompositionGeneration(ARGS, 'tok', cb, new AbortController().signal);
    expect(calls.job).toEqual([['j1', { source: 'auto', effort: 'medium' }]]);
    expect(calls.token).toEqual(['Hello ', 'world']);
    expect(calls.error).toEqual(['boom']);
  });

  it('reassembles a token frame split across chunk boundaries', async () => {
    // the JSON line arrives in two reads — the partial-line buffer must stitch it
    const frames = ['data: {"type":"to', 'ken","delta":"abc"}\n'];
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse(frames));
    const { cb, calls } = sink();
    await runCompositionGeneration(ARGS, 'tok', cb, new AbortController().signal);
    expect(calls.token).toEqual(['abc']);
  });

  it('polls a 202 batch job to completion and surfaces the result text (selection-edit)', async () => {
    const res = {
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({ job_id: 'j9', status: 'pending' }),
    } as unknown as Response;
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(res);
    (compositionApi.awaitJob as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 'completed', result: { text: 'edited prose' } });
    const { cb, calls } = sink();
    await runCompositionGeneration({ ...ARGS, selection: 'old text', operation: 'rewrite' }, 'tok', cb, new AbortController().signal);
    expect(calls.job).toEqual([['j9', undefined]]);
    expect(calls.text).toEqual(['edited prose']);
    expect(calls.error).toEqual([]);
  });

  it('surfaces a failed batch job error', async () => {
    const res = { ok: true, headers: { get: () => 'application/json' }, json: async () => ({ job_id: 'j9', status: 'pending' }) } as unknown as Response;
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(res);
    (compositionApi.awaitJob as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 'failed', result: { error: 'model exploded' } });
    const { cb, calls } = sink();
    await runCompositionGeneration({ ...ARGS, selection: 'x' }, 'tok', cb, new AbortController().signal);
    expect(calls.error).toEqual(['model exploded']);
  });

  it('emits an error on a non-ok response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 503, headers: { get: () => '' } } as unknown as Response);
    const { cb, calls } = sink();
    await runCompositionGeneration(ARGS, 'tok', cb, new AbortController().signal);
    expect(calls.error).toEqual(['generate failed (503)']);
  });

  it('does not clobber when the run is aborted mid-batch-poll (superseded)', async () => {
    const ctrl = new AbortController();
    const res = { ok: true, headers: { get: () => 'application/json' }, json: async () => ({ job_id: 'j9', status: 'pending' }) } as unknown as Response;
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(res);
    (compositionApi.awaitJob as ReturnType<typeof vi.fn>).mockImplementation(async () => { ctrl.abort(); return { status: 'completed', result: { text: 'late' } }; });
    const { cb, calls } = sink();
    await runCompositionGeneration({ ...ARGS, selection: 'x' }, 'tok', cb, ctrl.signal);
    expect(calls.text).toEqual([]);   // aborted → must not surface the superseded result
  });

  it('POSTs to selection-edit with a selection, generate otherwise', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(streamResponse([]));
    const { cb } = sink();
    await runCompositionGeneration(ARGS, 'tok', cb, new AbortController().signal);
    expect(String(f.mock.calls[0][0])).toContain('/generate');
    await runCompositionGeneration({ ...ARGS, selection: 'sel' }, 'tok', cb, new AbortController().signal);
    expect(String(f.mock.calls[1][0])).toContain('/selection-edit');
  });
});
