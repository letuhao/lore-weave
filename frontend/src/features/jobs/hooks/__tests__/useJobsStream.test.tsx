import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { useJobsStream } from '../useJobsStream';

vi.mock('../../api', () => ({ jobsApi: { streamUrl: () => 'http://x/v1/jobs/stream' } }));

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(c) {
      if (i < chunks.length) c.enqueue(enc.encode(chunks[i++]));
      else c.close();
    },
  });
}

afterEach(() => vi.restoreAllMocks());

describe('useJobsStream (fetch-stream SSE reader)', () => {
  it('sends the bearer in the Authorization header (not the URL)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: streamFrom([]) });
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = renderHook(() => useJobsStream('tok', vi.fn()));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://x/v1/jobs/stream');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
    expect(url).not.toContain('token=');
    unmount();
  });

  it('parses data: frames and skips comments/heartbeats', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: streamFrom([
        ': connected\n\n',
        'data: {"service":"knowledge","job_id":"j1","status":"running"}\n\n',
        ': heartbeat\n\n',
      ]),
    }));
    const onEvent = vi.fn();
    const { unmount } = renderHook(() => useJobsStream('tok', onEvent));
    await waitFor(() => expect(onEvent).toHaveBeenCalledTimes(1));
    expect(onEvent.mock.calls[0][0]).toMatchObject({ job_id: 'j1', status: 'running' });
    unmount();
  });

  it('stays idle and does not fetch when there is no token', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useJobsStream(null, vi.fn()));
    expect(result.current).toBe('idle');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does NOT reconnect on a 401 (expired token is terminal, not transient)', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 401, ok: false, body: null });
    vi.stubGlobal('fetch', fetchMock);
    const { result, unmount } = renderHook(() => useJobsStream('tok', vi.fn()));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    // Wait well past the 1s min backoff — a transient failure would reconnect by now.
    await new Promise((r) => setTimeout(r, 1200));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current).toBe('idle');
    unmount();
  });

  it('reconnects after a failed connection', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, body: null })
      .mockResolvedValueOnce({
        ok: true,
        body: streamFrom(['data: {"service":"k","job_id":"j2","status":"running"}\n\n']),
      });
    vi.stubGlobal('fetch', fetchMock);
    const onEvent = vi.fn();
    const { unmount } = renderHook(() => useJobsStream('tok', onEvent));
    await waitFor(() => expect(onEvent).toHaveBeenCalled(), { timeout: 3000 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    unmount();
  });
});
