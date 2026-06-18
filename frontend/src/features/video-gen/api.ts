import { apiBase } from '@/api';

// Shared base (relative '' default → proxy→gateway).
const base = apiBase;

export type GenerateVideoResponse = {
  status: 'completed' | 'pending' | 'running' | 'failed' | 'cancelled' | 'not_implemented';
  // LLM re-arch Phase 3 M5 — the decoupled job id (null on the inline path).
  job_id?: string | null;
  video_url: string | null;
  thumbnail_url?: string | null;
  message: string | null;
  error?: string | null;
  model: string | null;
  duration_seconds: number | null;
  size_bytes: number | null;
  content_type?: string | null;
};

// LLM re-arch Phase 3 M5 — when VIDEO_GEN_DECOUPLE_ENABLED is on, POST /generate
// answers 202 `{ job_id, status: 'pending' }` instead of a blocking 201; we poll
// GET /v1/video-gen/jobs/{id} to terminal. Video gen runs 5-20 min, so poll
// slowly with a generous ceiling. Flag-off (inline 201) returns directly.
const JOB_POLL_INTERVAL_MS = 3000;
const JOB_POLL_MAX = 600; // 600 × 3s = 30 min

const _sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function _getJob(jobId: string, token: string): Promise<GenerateVideoResponse> {
  const res = await fetch(`${base()}/v1/video-gen/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await res.json();
  if (!res.ok) {
    throw Object.assign(new Error(data?.detail || data?.message || res.statusText), {
      status: res.status,
    });
  }
  return data as GenerateVideoResponse;
}

// Normalize the terminal shape so the caller's `result.message` works whether
// the failure came back as `message` (inline) or `error` (decoupled poll).
function _normalize(r: GenerateVideoResponse): GenerateVideoResponse {
  return { ...r, message: r.message ?? r.error ?? null };
}

export const videoGenApi = {
  async generate(
    token: string,
    body: {
      prompt: string;
      model_source?: string;
      model_ref?: string;
      duration_seconds?: number;
      aspect_ratio?: string;
      style?: string;
    },
  ): Promise<GenerateVideoResponse> {
    const res = await fetch(`${base()}/v1/video-gen/generate`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      throw Object.assign(new Error(data?.detail || data?.message || res.statusText), {
        status: res.status,
      });
    }

    // Inline path (flag off): the 201 result is already terminal.
    if (!(data?.job_id && (data.status === 'pending' || data.status === 'running'))) {
      return _normalize(data as GenerateVideoResponse);
    }

    // Decoupled path (flag on): poll the job row to terminal. The caller's
    // "await the result" contract is unchanged — it never sees the 202.
    const jobId = data.job_id as string;
    for (let i = 0; i < JOB_POLL_MAX; i++) {
      await _sleep(JOB_POLL_INTERVAL_MS);
      const job = await _getJob(jobId, token);
      if (job.status !== 'pending' && job.status !== 'running') {
        return _normalize(job);
      }
    }
    throw Object.assign(new Error('Video generation timed out'), { status: 504 });
  },
};
