import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useCompositionStream } from '../useCompositionStream';

function sseResponse(frames: object[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(`data: ${JSON.stringify(f)}\n\n`));
      controller.close();
    },
  });
  return { ok: true, status: 200, body } as unknown as Response;
}

afterEach(() => vi.restoreAllMocks());

describe('useCompositionStream', () => {
  it('accumulates token deltas into the FE-local ghost buffer', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      sseResponse([
        { type: 'job', job_id: 'job-1', created: true, grounding_available: true },
        { type: 'token', delta: 'Hello ' },
        { type: 'token', delta: 'world' },
        { type: 'done', job_id: 'job-1', status: 'completed' },
      ]),
    );
    const { result } = renderHook(() => useCompositionStream('tok'));
    await act(async () => {
      await result.current.start({ projectId: 'p', outlineNodeId: 'n', modelSource: 'user_model', modelRef: 'm' });
    });
    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.ghost).toBe('Hello world');
    expect(result.current.jobId).toBe('job-1');
  });

  it('surfaces an error frame and never throws', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      sseResponse([
        { type: 'token', delta: 'partial' },
        { type: 'error', error: 'gateway down' },
      ]),
    );
    const { result } = renderHook(() => useCompositionStream('tok'));
    await act(async () => {
      await result.current.start({ projectId: 'p', outlineNodeId: 'n', modelSource: 'user_model', modelRef: 'm' });
    });
    await waitFor(() => expect(result.current.error).toBe('gateway down'));
    expect(result.current.ghost).toBe('partial'); // partial prose preserved
  });

  it('clearGhost empties the buffer (Discard)', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      sseResponse([{ type: 'token', delta: 'draft' }, { type: 'done', job_id: 'j', status: 'completed' }]),
    );
    const { result } = renderHook(() => useCompositionStream('tok'));
    await act(async () => {
      await result.current.start({ projectId: 'p', outlineNodeId: 'n', modelSource: 'user_model', modelRef: 'm' });
    });
    await waitFor(() => expect(result.current.ghost).toBe('draft'));
    act(() => result.current.clearGhost());
    expect(result.current.ghost).toBe('');
  });

  it('a superseded stream does not clobber the newer one (rapid re-generate)', async () => {
    // start#1 hangs (never closes); start#2 supersedes it. When #1's read is
    // aborted, its finally must NOT clear the newer controller / streaming flag.
    let firstController: ReadableStreamDefaultController<Uint8Array> | null = null;
    const hanging = { ok: true, status: 200, body: new ReadableStream<Uint8Array>({ start(ctrl) { firstController = ctrl; } }) } as unknown as Response;
    const encoder = new TextEncoder();
    const second = { ok: true, status: 200, body: new ReadableStream<Uint8Array>({
      start(ctrl) { ctrl.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'token', delta: 'second' })}\n\n`)); ctrl.close(); },
    }) } as unknown as Response;
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(hanging).mockResolvedValueOnce(second);

    const { result } = renderHook(() => useCompositionStream('tok'));
    act(() => { void result.current.start({ projectId: 'p', outlineNodeId: 'n', modelSource: 'user_model', modelRef: 'm' }); });
    await act(async () => {
      await result.current.start({ projectId: 'p', outlineNodeId: 'n', modelSource: 'user_model', modelRef: 'm' });
    });
    // #2 produced 'second'; #1's late abort must not have nulled state.
    await waitFor(() => expect(result.current.ghost).toBe('second'));
    expect(result.current.streaming).toBe(false);
    // No leak: the hook cancels start#1's reader on abort (controller-signal →
    // reader.cancel()), so its pending read() resolves {done:true} and the async
    // loop terminates even though this mock stream never closes on its own.
    void firstController;
  });

  it('cancels the in-flight reader on stop — no leaked read on a hanging stream', async () => {
    // Regression: useCompositionStream must explicitly cancel the reader when
    // aborted, not rely on fetch propagating the signal to the stream. Here the
    // stream NEVER enqueues or closes; stop() must still terminate the read
    // (its `cancel` hook fires) so the async loop doesn't leak forever (hang).
    let cancelled = false;
    const hanging = {
      ok: true, status: 200,
      body: new ReadableStream<Uint8Array>({ start() { /* never closes */ }, cancel() { cancelled = true; } }),
    } as unknown as Response;
    vi.spyOn(global, 'fetch').mockResolvedValue(hanging);

    const { result } = renderHook(() => useCompositionStream('tok'));
    act(() => { void result.current.start({ projectId: 'p', outlineNodeId: 'n', modelSource: 'user_model', modelRef: 'm' }); });
    await waitFor(() => expect(result.current.streaming).toBe(true));

    act(() => result.current.stop());
    await waitFor(() => expect(cancelled).toBe(true)); // reader.cancel() reached the stream
    expect(result.current.streaming).toBe(false);
  });

  it('does not stream when the response is not ok', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({ ok: false, status: 502, body: null } as unknown as Response);
    const { result } = renderHook(() => useCompositionStream('tok'));
    await act(async () => {
      await result.current.start({ projectId: 'p', outlineNodeId: 'n', modelSource: 'user_model', modelRef: 'm' });
    });
    await waitFor(() => expect(result.current.error).toContain('502'));
    expect(result.current.ghost).toBe('');
  });
});
