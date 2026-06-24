"""loreweave_jobs.scheduler — Redis-backed WFQ (weighted-fair-queue) scheduler for
the Unified Job Control Plane P5 (fair scheduling & per-tenant concurrency).

The multi-tenant "noisy neighbor" fix: one owner's giant multi-unit job (a 4000-
chapter translation/extraction) must not monopolize the worker fleet. This primitive
enforces, per **lane** (a dispatch domain, e.g. ``translation:chapter``):

- a **per-owner in-flight cap** — at most ``cap`` units of one ``owner_user_id`` run
  concurrently (the single biggest win — bounds any one owner to ``cap`` worker slots);
- **round-robin fairness across owners** (WFQ) — a new owner's units interleave with a
  giant job rather than queueing behind all of it;
- an optional **global budget** — total in-flight across all owners ≤ ``budget``.

Two substrates use it (see ``docs/plans/2026-06-16-p5-fair-scheduling.md``):

- **PUSH** (translation, lore-enrichment): the coordinator ``enqueue``s units instead of
  publishing them all; a dispatcher loop ``dispatch``es round-robin and publishes the
  released units; the worker ``release``s on terminal.
- **PULL** (knowledge/worker-ai poll loop): no ready queue — the loop iterates owners
  round-robin and gates each unit with ``acquire`` / ``release`` (same cap accounting).

Correctness:
- Every mutation is a **single Lua script** → atomic, race-free under concurrent workers.
- In-flight is a **ZSET of lease tokens → expiry** (not a bare counter): the lease TTL is
  a **crash-leak backstop** (a dead worker's slot frees after the TTL even if its
  ``release`` never runs); the worker's own ``finally: release`` is the fast path.
- ``reclaim_expired`` periodically recomputes the global total from truth (self-healing)
  and re-arms the ring for owners whose slots freed — so a crash can't permanently
  shrink the budget or strand a capped owner.

Redis keys (per lane, prefix ``p5:{lane}:``): ``ready:{owner}`` LIST · ``ring`` LIST +
``ring:member`` SET (round-robin ring, one entry/owner) · ``inflight:{owner}`` ZSET
(token→expiry) · ``inflight_total`` INT · ``active_owners`` SET · ``token_seq`` INT.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import redis.asyncio as aioredis

# Defaults (overridable per call / via the consuming service's env).
DEFAULT_OWNER_CAP = 5
DEFAULT_GLOBAL_BUDGET = 0  # 0 / negative ⇒ unlimited (cap is then the only limit)
DEFAULT_LEASE_TTL_MS = 3_600_000  # 1h — must exceed the longest single unit's runtime
DEFAULT_MAX_BATCH = 64


def _prefix(lane: str) -> str:
    return f"p5:{lane}:"


# ── Lua scripts (atomic) ─────────────────────────────────────────────────────────

# enqueue: RPUSH the unit onto the owner's ready list; add the owner to the ring once.
# KEYS[1]=ready:{owner}  KEYS[2]=ring  KEYS[3]=ring:member   ARGV[1]=owner ARGV[2]=unit
_ENQUEUE = """
redis.call('RPUSH', KEYS[1], ARGV[2])
if redis.call('SADD', KEYS[3], ARGV[1]) == 1 then
  redis.call('RPUSH', KEYS[2], ARGV[1])
end
return redis.call('LLEN', KEYS[1])
"""

# dispatch: round-robin release up to max_batch units, each owner gated by `cap` and the
# global `budget`. Returns a flat [token1, unit1, token2, unit2, ...]. Terminates: every
# iteration either removes an owner from the ring (no dispatch) or increments `dispatched`
# (bounded by max_batch); the ring is finite.
# KEYS[1]=ring KEYS[2]=ring:member KEYS[3]=inflight_total KEYS[4]=token_seq KEYS[5]=active_owners
# ARGV[1]=prefix ARGV[2]=cap ARGV[3]=budget ARGV[4]=max_batch ARGV[5]=now_ms ARGV[6]=ttl_ms
_DISPATCH = """
local prefix = ARGV[1]
local cap = tonumber(ARGV[2])
local budget = tonumber(ARGV[3])
local max_batch = tonumber(ARGV[4])
local now = tonumber(ARGV[5])
local ttl = tonumber(ARGV[6])
local ring = KEYS[1]
local ring_member = KEYS[2]
local total_key = KEYS[3]
local seq_key = KEYS[4]
local active = KEYS[5]
local out = {}
local dispatched = 0
while dispatched < max_batch do
  if budget > 0 then
    local total = tonumber(redis.call('GET', total_key) or '0')
    if total >= budget then break end
  end
  local owner = redis.call('LPOP', ring)
  if not owner then break end
  local ready_key = prefix .. 'ready:' .. owner
  local inflight_key = prefix .. 'inflight:' .. owner
  redis.call('ZREMRANGEBYSCORE', inflight_key, '-inf', now)
  local cur = redis.call('ZCARD', inflight_key)
  local nready = redis.call('LLEN', ready_key)
  if nready == 0 then
    redis.call('SREM', ring_member, owner)
  elseif cur >= cap then
    redis.call('SREM', ring_member, owner)
  else
    local unit = redis.call('LPOP', ready_key)
    -- Deterministic lease token when the unit carries one (`_p5_tok`): lets a
    -- DIFFERENT process release the slot by recomputing the token from its own data
    -- (e.g. a decoupled finalize keyed by job_id:chapter_id) without threading the
    -- dispatch-time token through an async pipeline. Falls back to an opaque owner:seq.
    local token
    local ok, u = pcall(cjson.decode, unit)
    if ok and type(u) == 'table' and u['_p5_tok'] then
      token = u['_p5_tok']
    else
      local seq = redis.call('INCR', seq_key)
      token = owner .. ':' .. seq
    end
    redis.call('ZADD', inflight_key, now + ttl, token)
    redis.call('INCR', total_key)
    redis.call('SADD', active, owner)
    out[#out+1] = token
    out[#out+1] = unit
    dispatched = dispatched + 1
    if redis.call('LLEN', ready_key) > 0 and (cur + 1) < cap then
      redis.call('RPUSH', ring, owner)
    else
      redis.call('SREM', ring_member, owner)
    end
  end
end
return out
"""

# acquire (pull model): claim one slot for `owner` if under cap; return a lease token or
# false. KEYS[1]=inflight:{owner} KEYS[2]=inflight_total KEYS[3]=token_seq KEYS[4]=active_owners
# ARGV[1]=cap ARGV[2]=now_ms ARGV[3]=ttl_ms ARGV[4]=owner
_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])
local cur = redis.call('ZCARD', KEYS[1])
if cur >= tonumber(ARGV[1]) then return false end
local seq = redis.call('INCR', KEYS[3])
local token = ARGV[4] .. ':' .. seq
redis.call('ZADD', KEYS[1], tonumber(ARGV[2]) + tonumber(ARGV[3]), token)
redis.call('INCR', KEYS[2])
redis.call('SADD', KEYS[4], ARGV[4])
return token
"""

# release: free a lease token; floor the total at 0; re-arm the ring if the owner still
# has ready work (so a capped owner resumes after a slot frees); drop from active when
# empty. KEYS[1]=inflight:{owner} KEYS[2]=inflight_total KEYS[3]=ready:{owner}
# KEYS[4]=ring KEYS[5]=ring:member KEYS[6]=active_owners   ARGV[1]=owner ARGV[2]=token
_RELEASE = """
local removed = redis.call('ZREM', KEYS[1], ARGV[2])
if removed == 1 then
  local t = redis.call('DECR', KEYS[2])
  if t < 0 then redis.call('SET', KEYS[2], '0') end
end
if redis.call('ZCARD', KEYS[1]) == 0 then
  redis.call('SREM', KEYS[6], ARGV[1])
end
if redis.call('LLEN', KEYS[3]) > 0 then
  if redis.call('SADD', KEYS[5], ARGV[1]) == 1 then
    redis.call('RPUSH', KEYS[4], ARGV[1])
  end
end
return removed
"""

# reclaim_expired: periodic crash backstop — drop expired leases across all active owners,
# recompute the global total from truth (self-heal), and re-arm the ring for owners with
# ready work. KEYS[1]=active_owners KEYS[2]=inflight_total KEYS[3]=ring KEYS[4]=ring:member
# ARGV[1]=prefix ARGV[2]=now_ms
_RECLAIM = """
local owners = redis.call('SMEMBERS', KEYS[1])
local total = 0
for i=1,#owners do
  local o = owners[i]
  local ik = ARGV[1] .. 'inflight:' .. o
  local rk = ARGV[1] .. 'ready:' .. o
  redis.call('ZREMRANGEBYSCORE', ik, '-inf', ARGV[2])
  local c = redis.call('ZCARD', ik)
  if c == 0 then
    redis.call('SREM', KEYS[1], o)
  else
    total = total + c
  end
  if redis.call('LLEN', rk) > 0 then
    if redis.call('SADD', KEYS[4], o) == 1 then redis.call('RPUSH', KEYS[3], o) end
  end
end
redis.call('SET', KEYS[2], total)
return total
"""


class FairScheduler:
    """Async WFQ scheduler over a single Redis. One instance can serve many lanes;
    ``cap`` / ``budget`` / ``lease_ttl_ms`` default here and can be overridden per call."""

    def __init__(
        self,
        redis_url: str,
        *,
        owner_cap: int = DEFAULT_OWNER_CAP,
        global_budget: int = DEFAULT_GLOBAL_BUDGET,
        lease_ttl_ms: int = DEFAULT_LEASE_TTL_MS,
        redis_client: Optional[aioredis.Redis] = None,
    ) -> None:
        self._redis_url = redis_url
        self.owner_cap = owner_cap
        self.global_budget = global_budget
        self.lease_ttl_ms = lease_ttl_ms
        self._redis: Optional[aioredis.Redis] = redis_client
        self._scripts: dict[str, Any] = {}

    async def _r(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        if not self._scripts:
            self._scripts = {
                "enqueue": self._redis.register_script(_ENQUEUE),
                "dispatch": self._redis.register_script(_DISPATCH),
                "acquire": self._redis.register_script(_ACQUIRE),
                "release": self._redis.register_script(_RELEASE),
                "reclaim": self._redis.register_script(_RECLAIM),
            }
        return self._redis

    @staticmethod
    def _now_ms() -> int:
        # Wall clock for lease expiry. Imported lazily so the module stays import-safe in
        # environments that stub time; monotonicity across processes uses the Redis server
        # only via the relative ttl, so small clock skew just shifts the backstop window.
        import time

        return int(time.time() * 1000)

    # ── PUSH model ────────────────────────────────────────────────────────────────
    async def enqueue(self, lane: str, owner: str, unit: dict) -> int:
        """Queue one unit for ``owner`` on ``lane``. Returns the owner's ready depth."""
        r = await self._r()
        p = _prefix(lane)
        return int(
            await self._scripts["enqueue"](
                keys=[f"{p}ready:{owner}", f"{p}ring", f"{p}ring:member"],
                args=[owner, json.dumps(unit)],
            )
        )

    async def dispatch(
        self,
        lane: str,
        *,
        cap: Optional[int] = None,
        budget: Optional[int] = None,
        max_batch: int = DEFAULT_MAX_BATCH,
        lease_ttl_ms: Optional[int] = None,
    ) -> list[tuple[str, dict]]:
        """Round-robin release up to ``max_batch`` units (≤ ``cap``/owner, ≤ ``budget``
        total). Returns ``[(lease_token, unit), …]`` — the caller publishes each unit
        (carrying its token) to the worker substrate, then the worker ``release``s it."""
        r = await self._r()
        p = _prefix(lane)
        raw = await self._scripts["dispatch"](
            keys=[f"{p}ring", f"{p}ring:member", f"{p}inflight_total", f"{p}token_seq", f"{p}active_owners"],
            args=[
                p,
                cap if cap is not None else self.owner_cap,
                budget if budget is not None else self.global_budget,
                max_batch,
                self._now_ms(),
                lease_ttl_ms if lease_ttl_ms is not None else self.lease_ttl_ms,
            ],
        )
        out: list[tuple[str, dict]] = []
        for i in range(0, len(raw), 2):
            out.append((raw[i], json.loads(raw[i + 1])))
        return out

    # ── PULL model ────────────────────────────────────────────────────────────────
    async def acquire(
        self, lane: str, owner: str, *, cap: Optional[int] = None, lease_ttl_ms: Optional[int] = None
    ) -> Optional[str]:
        """Claim one in-flight slot for ``owner`` if under ``cap``. Returns a lease token
        to pass to ``release``, or ``None`` when the owner is at cap."""
        r = await self._r()
        p = _prefix(lane)
        token = await self._scripts["acquire"](
            keys=[f"{p}inflight:{owner}", f"{p}inflight_total", f"{p}token_seq", f"{p}active_owners"],
            args=[
                cap if cap is not None else self.owner_cap,
                self._now_ms(),
                lease_ttl_ms if lease_ttl_ms is not None else self.lease_ttl_ms,
                owner,
            ],
        )
        return token or None

    async def release(self, lane: str, owner: str, token: str) -> bool:
        """Free a lease token (PUSH or PULL). Idempotent — returns True iff it removed a
        live lease (a double-release or an already-expired token returns False)."""
        r = await self._r()
        p = _prefix(lane)
        removed = await self._scripts["release"](
            keys=[
                f"{p}inflight:{owner}", f"{p}inflight_total", f"{p}ready:{owner}",
                f"{p}ring", f"{p}ring:member", f"{p}active_owners",
            ],
            args=[owner, token],
        )
        return bool(removed)

    async def reclaim_expired(self, lane: str) -> int:
        """Crash backstop: drop expired leases across owners, recompute the total from
        truth, re-arm the ring. Returns the recomputed in-flight total. Run periodically."""
        r = await self._r()
        p = _prefix(lane)
        return int(
            await self._scripts["reclaim"](
                keys=[f"{p}active_owners", f"{p}inflight_total", f"{p}ring", f"{p}ring:member"],
                args=[p, self._now_ms()],
            )
        )

    # ── observability (tests / GUI) ───────────────────────────────────────────────
    async def inflight_count(self, lane: str, owner: str) -> int:
        r = await self._r()
        return int(await r.zcard(f"{_prefix(lane)}inflight:{owner}"))

    async def ready_len(self, lane: str, owner: str) -> int:
        r = await self._r()
        return int(await r.llen(f"{_prefix(lane)}ready:{owner}"))

    async def inflight_total(self, lane: str) -> int:
        r = await self._r()
        return int(await r.get(f"{_prefix(lane)}inflight_total") or 0)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
