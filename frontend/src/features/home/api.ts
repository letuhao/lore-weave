// M2 — the platform home + activity API layer. All three routes are BFF read-composition
// (GET /v1/home, GET /v1/activity, POST /v1/activity/mark-all-read); owner is derived server-side
// from the JWT, so no id is ever sent from the client.
import { apiJson } from '@/api';
import type { ActivityFeedPage, HomeResponse } from './types';

export const homeApi = {
  getHome(token: string | null) {
    return apiJson<HomeResponse>('/v1/home', { token });
  },

  /** One keyset page of the activity feed. `cursor` is the opaque token from the previous page. */
  getActivity(token: string | null, cursor?: string, limit = 20) {
    const q = new URLSearchParams({ limit: String(limit) });
    if (cursor) q.set('cursor', cursor);
    return apiJson<ActivityFeedPage>(`/v1/activity?${q.toString()}`, { token });
  },

  markAllRead(token: string | null) {
    return apiJson<{ marked: number }>('/v1/activity/mark-all-read', { method: 'POST', token });
  },
};
