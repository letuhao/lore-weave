import { apiBase } from '@/api';

// Shared base (relative '' default → proxy→gateway).
const base = apiBase;

export type GenerateVideoResponse = {
  status: 'completed' | 'pending' | 'failed' | 'not_implemented';
  video_url: string | null;
  thumbnail_url: string | null;
  message: string | null;
  model: string | null;
  duration_seconds: number | null;
  size_bytes: number | null;
  content_type: string | null;
};

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
    return data;
  },
};
