import { Logger } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

/**
 * Book-access grant check against book-service (the grant authority, E0). In user-JWT mode the
 * KAL is the boundary for FE temporal reads — the BFF is a dumb passthrough that does NO grant
 * check — so the KAL MUST verify the user has a grant on the book before forwarding, or a user
 * could read any book's knowledge by guessing book ids. Mirrors the Go/Python grantclient:
 *   GET {book}/internal/books/{bookId}/access?user_id={userId}  → { grant_level, lifecycle_state }
 *
 * Access = a non-"none" grant_level on an active book. Positive results are cached briefly
 * (the book-service grant authority is the SoT; a short TTL bounds the staleness window while
 * sparing it a call per read). Negative results are NOT cached, so a freshly-granted user is
 * not locked out. Fail-closed: any error / non-200 → no access.
 */
const log = new Logger('kal-grants');
const POSITIVE_TTL_MS = 30_000;
const GRANT_TIMEOUT_MS = 5_000; // a hung book-service must not stall a user read forever
const CACHE_MAX = 10_000; // bound memory; sweep expired (then hard-clear) past this
const _cache = new Map<string, number>(); // key -> expiry epoch ms

function rememberPositive(key: string): void {
  if (_cache.size >= CACHE_MAX) {
    const now = Date.now();
    for (const [k, exp] of _cache) {
      if (exp <= now) _cache.delete(k);
    }
    if (_cache.size >= CACHE_MAX) _cache.clear(); // pathological burst — drop all (re-checks, fail-safe)
  }
  _cache.set(key, Date.now() + POSITIVE_TTL_MS);
}

export async function hasBookAccess(bookId: string, userId: string, signal?: AbortSignal): Promise<boolean> {
  const key = `${bookId}:${userId}`;
  const exp = _cache.get(key);
  if (exp !== undefined) {
    if (exp > Date.now()) return true;
    _cache.delete(key);
  }
  const cfg = loadConfig();
  const url = `${cfg.bookServiceUrl}/internal/books/${encodeURIComponent(bookId)}/access?user_id=${encodeURIComponent(userId)}`;
  let res: Response;
  try {
    // Timeout so a slow/hung book-service fails closed instead of hanging the read. Compose
    // the caller's abort signal (client disconnect) with the timeout when both are present.
    const timeout = AbortSignal.timeout(GRANT_TIMEOUT_MS);
    const sig = signal ? AbortSignal.any([signal, timeout]) : timeout;
    res = await fetch(url, { headers: { 'X-Internal-Token': cfg.internalToken }, signal: sig });
  } catch (e) {
    log.warn(`grant check failed for ${key}: ${(e as Error).message}`);
    return false; // fail closed (unreachable OR timed out)
  }
  if (!res.ok) return false; // 404 (no grant) / 5xx → no access
  let body: { grant_level?: string; lifecycle_state?: string };
  try {
    body = (await res.json()) as { grant_level?: string; lifecycle_state?: string };
  } catch {
    return false;
  }
  const level = (body.grant_level ?? '').toLowerCase();
  const lifecycle = (body.lifecycle_state ?? '').toLowerCase();
  const ok = level !== '' && level !== 'none' && (lifecycle === '' || lifecycle === 'active');
  if (ok) rememberPositive(key);
  return ok;
}
