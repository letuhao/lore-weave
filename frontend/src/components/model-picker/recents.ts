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

// The localStorage CACHE is scoped per user (review-impl W5 #1): the server
// pref is per-user by construction, but an unscoped cache key survives a
// logout/login on a shared browser — user A's model ids would seed user B's
// recents and pushRecent would write them into B's SERVER prefs.
function cacheKey(capability: string | undefined, userId: string | undefined): string {
  return `lw.${recentsPrefKey(capability)}.${userId || 'anon'}`;
}

function sanitize(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === 'string').slice(0, MAX_RECENTS);
}

/** Synchronous read from the localStorage cache (initial render). */
export function loadRecentsCached(capability?: string, userId?: string): string[] {
  try {
    const raw = localStorage.getItem(cacheKey(capability, userId));
    return raw ? sanitize(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

/** Async refresh from the server prefs; updates the cache. */
export async function loadRecentsFromServer(
  capability: string | undefined,
  token: string | null | undefined,
  userId?: string,
): Promise<string[] | undefined> {
  const value = await loadPrefFromServer<unknown>(recentsPrefKey(capability), token);
  if (value === undefined) return undefined;
  const recents = sanitize(value);
  try {
    localStorage.setItem(cacheKey(capability, userId), JSON.stringify(recents));
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
  userId?: string,
): string[] {
  const next = [
    userModelId,
    ...loadRecentsCached(capability, userId).filter((id) => id !== userModelId),
  ].slice(0, MAX_RECENTS);
  try {
    localStorage.setItem(cacheKey(capability, userId), JSON.stringify(next));
  } catch {
    /* cache only */
  }
  syncPrefsToServer(recentsPrefKey(capability), next, token);
  return next;
}
