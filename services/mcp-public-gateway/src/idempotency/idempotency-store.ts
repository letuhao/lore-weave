import { Logger } from '@nestjs/common';

/**
 * H-G — idempotency for headless public writes. A public agent that retries a
 * non-idempotent create (`book_create`, `composition_outline_node_create`, …)
 * after a dropped response would otherwise duplicate the row. When the agent
 * supplies an `idempotency_key` on a single Tier-A (`write_auto`) `tools/call`,
 * the edge dedups on `(key_id, tool, idempotency_key)`: the FIRST call relays and
 * its response is cached; a retry within the window REPLAYS the cached response
 * without re-executing; a concurrent retry while the first is still in flight gets
 * an explicit "in progress" error rather than a second execution.
 *
 * Scope (v1): SINGLE-message `write_auto` calls only. `write_confirm` is owned by
 * the propose→approve/divert path; batches are deferred (single-message only, like
 * the divert) → `D-PMCP-BATCH-IDEMPOTENCY`. The key is an EDGE concept — it is
 * stripped before relay so the underlying `ForbidExtra` tool never sees it; a
 * first-party (non-edge) caller is unaffected.
 *
 * Fail policy: idempotency is a best-effort retry-dedup. When the store is absent
 * (no REDIS_URL) or errors, we **fail OPEN** (relay without dedup — today's
 * behavior), never blocking a legitimate write. This is the opposite of the
 * rate-limiter's write-fail-CLOSED because blocking a write on a Redis blip is the
 * worse outcome here; the cost of failing open is at most a duplicate on a rare
 * concurrent retry during an outage.
 */

/** The minimal Redis surface idempotency needs — keeps it driver-free + testable. */
export interface IdempotencyStore {
  /**
   * Atomically claim `key` with `pendingValue` IF ABSENT (SET NX EX). Returns
   * `{won:true}` when we claimed it (caller proceeds to relay), else
   * `{won:false, value}` carrying the current value (the pending marker, or a
   * cached response from an earlier completed call). Throws on a backend error
   * (the service maps that to fail-open).
   */
  claimOrLoad(
    key: string,
    pendingValue: string,
    ttlSeconds: number,
  ): Promise<{ won: true } | { won: false; value: string }>;
  /** Overwrite `key` with the final response body (SET EX) — the replay cache. */
  store(key: string, value: string, ttlSeconds: number): Promise<void>;
  /** Drop `key` (a relay that errored must NOT be cached → let a retry re-attempt). */
  remove(key: string): Promise<void>;
}

/**
 * The pending sentinel. A real cached value is always a JSON-RPC response text
 * (starts with `{` or `[`), so this non-JSON marker can never collide with one —
 * `begin()` distinguishes "still in flight" from "cached response" by this value.
 */
export const PENDING_MARKER = '__mcp_idem_pending__';
/** Pending-claim TTL: a relay shouldn't outlast this; auto-clears a crashed claim. */
export const PENDING_TTL_SECONDS = 120;
/** Cached-response TTL: how long a completed result is replayable. */
export const RESULT_TTL_SECONDS = 86_400; // 24h
/** Don't cache an oversized body (a retry just re-executes — graceful degrade). */
export const MAX_CACHED_BYTES = 256 * 1024;

export type IdemBegin =
  /** We won the claim → relay, then call `complete()` (ok) or `abort()` (errored). */
  | { kind: 'proceed' }
  /** Another in-flight request holds the claim → return an "in progress" error. */
  | { kind: 'pending' }
  /** A cached response exists → replay it verbatim, do NOT relay. */
  | { kind: 'replay'; text: string };

export class Idempotency {
  private readonly log = new Logger(Idempotency.name);
  private warnedNoStore = false;

  // `store` is null when REDIS_URL is unset → idempotency disabled (fail-open).
  constructor(private readonly store: IdempotencyStore | null) {}

  /** Claim the dedup slot for `key`, or surface a replay/pending decision. */
  async begin(key: string): Promise<IdemBegin> {
    if (!this.store) {
      if (!this.warnedNoStore) {
        this.log.warn('idempotency DISABLED (no REDIS_URL) — public write retries are not deduped; set REDIS_URL in any real deployment');
        this.warnedNoStore = true;
      }
      return { kind: 'proceed' };
    }
    try {
      const r = await this.store.claimOrLoad(key, PENDING_MARKER, PENDING_TTL_SECONDS);
      if (r.won) return { kind: 'proceed' };
      return r.value === PENDING_MARKER ? { kind: 'pending' } : { kind: 'replay', text: r.value };
    } catch (e) {
      // Fail OPEN — a store blip must not block a write; degrade to no-dedup.
      this.log.warn(`idempotency store error (failing OPEN, no dedup): ${e}`);
      return { kind: 'proceed' };
    }
  }

  /** Cache a successful relay's response under `key` (replaces the pending marker). */
  async complete(key: string, text: string): Promise<void> {
    if (!this.store) return;
    if (Buffer.byteLength(text, 'utf8') > MAX_CACHED_BYTES) {
      // Too big to cache — drop the pending marker so a retry re-executes rather
      // than getting stuck "pending" until TTL.
      await this.abort(key);
      return;
    }
    try {
      await this.store.store(key, text, RESULT_TTL_SECONDS);
    } catch (e) {
      this.log.warn(`idempotency store write failed (replay cache skipped): ${e}`);
    }
  }

  /** Release the claim for `key` (an errored relay must be retryable, not cached). */
  async abort(key: string): Promise<void> {
    if (!this.store) return;
    try {
      await this.store.remove(key);
    } catch (e) {
      this.log.warn(`idempotency store remove failed (stale pending until TTL): ${e}`);
    }
  }
}
