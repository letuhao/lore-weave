// M5 (D-MOB-4) — the Web Push client API. All routes ride the gateway's notification proxy
// (/v1/notifications/*). Owner is server-derived from the JWT; the client never sends an id.
import { apiJson } from '@/api';

export interface VapidInfo {
  public_key: string;
  configured: boolean;
}
export interface PushPrefs {
  topics: Record<string, boolean>;
  source: Record<string, string>;
}

export const pushApi = {
  getVapidKey(token: string | null) {
    return apiJson<VapidInfo>('/v1/notifications/push/vapid-public-key', { token });
  },
  register(token: string | null, sub: PushSubscriptionJSON) {
    return apiJson<{ registered: boolean }>('/v1/notifications/push-subscriptions', {
      method: 'POST',
      token,
      body: JSON.stringify(sub),
    });
  },
  unregister(token: string | null, endpoint: string) {
    return apiJson<{ deleted: number }>(
      `/v1/notifications/push-subscriptions?endpoint=${encodeURIComponent(endpoint)}`,
      { method: 'DELETE', token },
    );
  },
  getPreferences(token: string | null) {
    return apiJson<PushPrefs>('/v1/notifications/push-preferences', { token });
  },
  setPreference(token: string | null, push_topic: string, push_enabled: boolean) {
    return apiJson<{ push_topic: string; push_enabled: boolean }>('/v1/notifications/push-preferences', {
      method: 'PUT',
      token,
      body: JSON.stringify({ push_topic, push_enabled }),
    });
  },
};

// urlBase64ToUint8Array — the VAPID public key arrives base64url; PushManager.subscribe needs a
// Uint8Array applicationServerKey. Standard conversion.
export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  // Explicit ArrayBuffer (not the ambient ArrayBufferLike) so it satisfies BufferSource /
  // applicationServerKey under strict TS.
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}
