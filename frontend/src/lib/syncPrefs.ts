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
 * Awaitable write-through of a single preference key. Unlike syncPrefsToServer
 * (fire-and-forget), this resolves only after the PATCH settles, so a caller can
 * order a follow-up action (e.g. navigation) AFTER the durable write. Resolves to
 * true on success, false on failure (caller decides whether to proceed anyway).
 */
export async function savePrefToServer(key: string, value: unknown, token: string | null | undefined): Promise<boolean> {
  if (!token) return false;
  try {
    await apiJson('/v1/me/preferences', {
      method: 'PATCH',
      token,
      body: JSON.stringify({ prefs: { [key]: value } }),
    });
    return true;
  } catch {
    return false;
  }
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
