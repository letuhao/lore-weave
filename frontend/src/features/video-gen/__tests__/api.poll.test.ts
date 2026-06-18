/**
 * videoGenApi.generate submit+poll (LLM re-arch Phase 3 M5).
 *
 * Flag OFF (inline 201): the response is already terminal → returned directly,
 * no poll. Flag ON (decoupled): POST answers 202 `{ job_id, status:'pending' }`;
 * generate() then polls GET /v1/video-gen/jobs/{id} to terminal and returns the
 * completed shape — the caller (VideoBlockNode) never sees the 202, its
 * "await the result" contract is unchanged. A failed job surfaces error→message.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { videoGenApi } from '../api';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const _BODY = { prompt: 'a cat', model_source: 'user_model', model_ref: 'm1', duration_seconds: 5, aspect_ratio: '16:9' };

function jsonRes(status: number, body: unknown): Response {
  return { ok: status < 400, status, json: async () => body } as unknown as Response;
}

describe('videoGenApi.generate (submit + poll)', () => {
  it('returns the inline 201 result directly when the flag is off (no poll)', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonRes(201, { status: 'completed', video_url: 'http://minio/v.mp4', duration_seconds: 5, size_bytes: 1024 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const out = await videoGenApi.generate('tok', _BODY);
    expect(out.status).toBe('completed');
    expect(out.video_url).toBe('http://minio/v.mp4');
    expect(fetchMock).toHaveBeenCalledTimes(1); // POST only, no /jobs poll
  });

  it('polls a 202 pending job to completion and maps the video URL', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonRes(202, { status: 'pending', job_id: 'vj1', video_url: null })) // POST 202
      .mockResolvedValueOnce(jsonRes(200, { status: 'running', video_url: null }))                 // poll 1
      .mockResolvedValueOnce(jsonRes(200, { status: 'completed', video_url: 'http://minio/done.mp4', size_bytes: 2048 })); // poll 2
    vi.stubGlobal('fetch', fetchMock);

    const p = videoGenApi.generate('tok', _BODY);
    await vi.runAllTimersAsync();
    const out = await p;

    expect(out.status).toBe('completed');
    expect(out.video_url).toBe('http://minio/done.mp4');
    expect(out.size_bytes).toBe(2048);
    expect(fetchMock).toHaveBeenCalledTimes(3); // POST + 2 polls
    expect((fetchMock.mock.calls[1][0] as string)).toContain('/v1/video-gen/jobs/vj1');
  });

  it('surfaces a failed job error as message (decoupled poll)', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonRes(202, { status: 'pending', job_id: 'vj2', video_url: null }))
      .mockResolvedValueOnce(jsonRes(200, { status: 'failed', video_url: null, error: 'model exploded' }));
    vi.stubGlobal('fetch', fetchMock);

    const p = videoGenApi.generate('tok', _BODY);
    await vi.runAllTimersAsync();
    const out = await p;

    expect(out.status).toBe('failed');
    expect(out.message).toBe('model exploded'); // error → message normalization
  });

  it('throws on a non-ok submit', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonRes(402, { detail: 'out of credits' }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(videoGenApi.generate('tok', _BODY)).rejects.toThrow('out of credits');
  });
});
