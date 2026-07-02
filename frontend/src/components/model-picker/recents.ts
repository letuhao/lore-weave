import { loadPrefFromServer, syncPrefsToServer } from '@/lib/syncPrefs';

/**
 * Per-capability "recently used models" for the shared ModelPicker.
 *
 * Persistence follows the platform rule: server (`/v1/me/preferences` via
 * syncPrefs) is the source of truth, localStorage is only the fast cache.
 * Key shape: `modelPicker.recents.<capability|any>` → string[] (user_model_ids,
 * most recent first, capped at 5).
 */
const MAX_RECENTS = 5;

export function recentsPrefKey(capability?: string): string {
  return `modelPicker.recents.${capability || 'any'}`;
}

function cacheKey(capability?: string): string {
  return `lw.${recentsPrefKey(capability)}`;
}

function sanitize(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === 'string').slice(0, MAX_RECENTS);
}

/** Synchronous read from the localStorage cache (initial render). */
export function loadRecentsCached(capability?: string): string[] {
  try {
    const raw = localStorage.getItem(cacheKey(capability));
    return raw ? sanitize(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

/** Async refresh from the server prefs; updates the cache. */
export async function loadRecentsFromServer(
  capability: string | undefined,
  token: string | null | undefined,
): Promise<string[] | undefined> {
  const value = await loadPrefFromServer<unknown>(recentsPrefKey(capability), token);
  if (value === undefined) return undefined;
  const recents = sanitize(value);
  try {
    localStorage.setItem(cacheKey(capability), JSON.stringify(recents));
  } catch {
    /* cache only */
  }
  return recents;
}

/** Record a selection: unshift + dedupe + cap; write-through cache + server. */
export function pushRecent(
  capability: string | undefined,
  userModelId: string,
  token: string | null | undefined,
): string[] {
  const next = [userModelId, ...loadRecentsCached(capability).filter((id) => id !== userModelId)].slice(
    0,
    MAX_RECENTS,
  );
  try {
    localStorage.setItem(cacheKey(capability), JSON.stringify(next));
  } catch {
    /* cache only */
  }
  syncPrefsToServer(recentsPrefKey(capability), next, token);
  return next;
}
