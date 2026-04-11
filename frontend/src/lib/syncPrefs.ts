import { apiJson } from '@/api';

/**
 * Sync a preference object to the server.
 * Uses PATCH /v1/me/preferences which does JSON merge (prefs || $2).
 * Fire-and-forget — localStorage is the fast cache, server is the source of truth.
 */
export function syncPrefsToServer(key: string, value: unknown, token: string | null | undefined): void {
  if (!token) return;
  apiJson('/v1/me/preferences', {
    method: 'PATCH',
    token,
    body: JSON.stringify({ prefs: { [key]: value } }),
  }).catch(() => { /* silent — localStorage is fallback */ });
}

/**
 * Load a preference key from the server-side prefs object.
 * Returns undefined if not found or not authenticated.
 */
export async function loadPrefFromServer<T>(key: string, token: string | null | undefined): Promise<T | undefined> {
  if (!token) return undefined;
  try {
    const res = await apiJson<{ prefs: Record<string, unknown> }>('/v1/me/preferences', { token });
    if (res.prefs && key in res.prefs) {
      return res.prefs[key] as T;
    }
  } catch { /* silent */ }
  return undefined;
}
