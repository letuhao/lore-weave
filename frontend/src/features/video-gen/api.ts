const base = () => import.meta.env.VITE_API_BASE || 'http://localhost:3000';

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

export type VideoModel = {
  id: string;
  name: string;
  provider: string;
  max_duration_seconds: number;
  supported_aspect_ratios: string[];
  supported_styles: string[];
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

  async listModels(token: string): Promise<{ items: VideoModel[] }> {
    const res = await fetch(`${base()}/v1/video-gen/models`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail || res.statusText);
    return data;
  },
};
