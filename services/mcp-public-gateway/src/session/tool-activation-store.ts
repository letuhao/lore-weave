/**
 * Per-SESSION activated-tool store — the backbone of the lazy tool-loading state machine.
 *
 * The public edge starts a session minimal (only `find_tools`) and the agent PROGRESSIVELY
 * activates tools via find_tools; the activated set is what `tools/list` advertises, so the
 * agent's visible surface grows deliberately within the session (ChatGPT/Anthropic-style
 * load-on-demand). The session is the gateway's stable per-key session (session_id = key_id),
 * so the set persists across the key's long-lived session with a SLIDING TTL that bounds an
 * idle session.
 *
 * Activation governs VISIBILITY (what tools/list shows) — NOT permission: a discovered tool is
 * still gated by `isToolAllowed` when actually called, so this never widens scope. Mirrors
 * `idempotency/redis-idempotency-store.ts`: the service depends on the abstract store, so it
 * stays driver-free + unit-testable. Unlike idempotency (null → disabled), this falls back to an
 * IN-MEMORY store when REDIS_URL is unset, so the state machine ALWAYS works (single-instance
 * dev / tests); multi-replica deployments set REDIS_URL for a shared session surface.
 */
import Redis from 'ioredis';

/** Sliding TTL for a session's activated set — bounds an idle session (24h). */
export const ACTIVATION_TTL_SECONDS = 86_400;

/** The minimal surface the activation state machine needs — keeps it driver-free + testable. */
export interface ToolActivationStore {
  /** Add `names` to the session's activated set + (re)set the sliding TTL. No-op on []. */
  activate(sessionId: string, names: string[], ttlSeconds: number): Promise<void>;
  /** The session's activated tool names; bumps the sliding TTL when non-empty. */
  activated(sessionId: string, ttlSeconds: number): Promise<string[]>;
}

function sessionKey(sessionId: string): string {
  return `pmcp:tools:${sessionId}`;
}

class RedisToolActivationStore implements ToolActivationStore {
  constructor(private readonly redis: Redis) {}

  async activate(sessionId: string, names: string[], ttlSeconds: number): Promise<void> {
    if (names.length === 0) return;
    const key = sessionKey(sessionId);
    await this.redis.sadd(key, ...names);
    await this.redis.expire(key, ttlSeconds);
  }

  async activated(sessionId: string, ttlSeconds: number): Promise<string[]> {
    const key = sessionKey(sessionId);
    const members = await this.redis.smembers(key);
    if (members.length > 0) await this.redis.expire(key, ttlSeconds); // sliding window
    return members;
  }
}

/** Hermetic in-memory store (dev / tests / single-instance). Lazy per-key expiry. */
export class InMemoryToolActivationStore implements ToolActivationStore {
  private readonly map = new Map<string, { names: Set<string>; expiresAt: number }>();

  // Monotonic-ish clock injected for tests; defaults to Date.now via a closure-free counter is
  // not needed — real time is fine here (TTL semantics, not security).
  constructor(private readonly now: () => number = () => Date.now()) {}

  private live(sessionId: string): Set<string> | null {
    const e = this.map.get(sessionId);
    if (!e) return null;
    if (e.expiresAt <= this.now()) {
      this.map.delete(sessionId);
      return null;
    }
    return e.names;
  }

  async activate(sessionId: string, names: string[], ttlSeconds: number): Promise<void> {
    if (names.length === 0) return;
    const existing = this.live(sessionId) ?? new Set<string>();
    for (const n of names) existing.add(n);
    this.map.set(sessionId, { names: existing, expiresAt: this.now() + ttlSeconds * 1000 });
  }

  async activated(sessionId: string, ttlSeconds: number): Promise<string[]> {
    const names = this.live(sessionId);
    if (!names) return [];
    // Sliding TTL: reading bumps the window (matches the Redis EXPIRE-on-read).
    this.map.set(sessionId, { names, expiresAt: this.now() + ttlSeconds * 1000 });
    return [...names];
  }
}

/**
 * Build a ToolActivationStore: Redis when REDIS_URL is set (shared, multi-replica), else an
 * in-memory store so the state machine still works (single-instance dev / tests). Shares the
 * idempotency store's lazy-connect + fail-fast settings.
 */
export function makeToolActivationStoreFromEnv(): ToolActivationStore {
  const url = process.env.REDIS_URL;
  if (!url) return new InMemoryToolActivationStore();
  const redis = new Redis(url, {
    maxRetriesPerRequest: 1,
    commandTimeout: 1000,
    enableOfflineQueue: false,
    lazyConnect: false,
  });
  redis.on('error', () => undefined);
  return new RedisToolActivationStore(redis);
}
