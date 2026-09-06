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

/**
 * The shared body of `hasBookAccess` and `hasProjectAccess` (T55/g, spec §8.7).
 *
 * Extracted rather than copied. Both call an `/access` endpoint that answers the SAME
 * contract — `{ grant_level, lifecycle_state }`, always 200, `"none"` for missing-or-forbidden
 * so neither can be used as an existence oracle — and every rule for reading that answer is
 * subtle in the same way: fail closed on transport error, fail closed on a non-200, cache
 * POSITIVES only so a freshly-granted user is not locked out, and treat an empty lifecycle as
 * not-disqualifying. A second hand-written copy would inherit whichever of those was current
 * the day it was written; §8.4 calls that "one concept, two readers" and names it a rot
 * pattern this migration actually hit.
 *
 * ⚠️ `key` is NAMESPACED by the caller (`book:` / `project:`). Without that, a project id
 * equal to a book id would share one cache entry and a grant on one would answer for the
 * other.
 */
async function hasAccessAt(url: string, key: string, signal?: AbortSignal): Promise<boolean> {
  const exp = _cache.get(key);
  if (exp !== undefined) {
    if (exp > Date.now()) return true;
    _cache.delete(key);
  }
  const cfg = loadConfig();
  let res: Response;
  try {
    // Timeout so a slow/hung authority fails closed instead of hanging the read. Compose
    // the caller's abort signal (client disconnect) with the timeout when both are present.
    const timeout = AbortSignal.timeout(GRANT_TIMEOUT_MS);
    const sig = signal ? AbortSignal.any([signal, timeout]) : timeout;
    res = await fetch(url, { headers: { 'X-Internal-Token': cfg.internalToken }, signal: sig });
  } catch (e) {
    log.warn(`grant check failed for ${key}: ${(e as Error).message}`);
    return false; // fail closed (unreachable OR timed out)
  }
  if (!res.ok) return false; // 404 (no grant) / 5xx -> no access
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

/**
 * Project-access grant check against knowledge-service, the owner of projects (T55/g).
 *
 * `KalAuthGuard`'s user-mode arm needs `req.params.bookId`, so a project-scoped KAL route has
 * no user-mode door without this. §8.7 rejected resolving project -> book inside the gateway:
 * `knowledge_projects.book_id` belongs to the owning service, and a project with no book (or
 * two) would be adjudicated in the wrong place. The owning service applies its OWN rule
 * (owner wins; a project with a book defers to the book grant; a book-less project is
 * owner-only, R1) and answers with a level.
 */
export async function hasProjectAccess(projectId: string, userId: string, signal?: AbortSignal): Promise<boolean> {
  const cfg = loadConfig();
  const url = `${cfg.knowledgeUrl}/internal/projects/${encodeURIComponent(projectId)}/access?user_id=${encodeURIComponent(userId)}`;
  return hasAccessAt(url, `project:${projectId}:${userId}`, signal);
}

export async function hasBookAccess(bookId: string, userId: string, signal?: AbortSignal): Promise<boolean> {
  const cfg = loadConfig();
  const url = `${cfg.bookServiceUrl}/internal/books/${encodeURIComponent(bookId)}/access?user_id=${encodeURIComponent(userId)}`;
  return hasAccessAt(url, `book:${bookId}:${userId}`, signal);
}
