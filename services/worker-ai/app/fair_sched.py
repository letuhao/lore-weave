"""P5 fair-scheduling wiring for knowledge extraction (the PULL substrate).

Lane ``knowledge:extraction``: unlike translation (PUSH — a coordinator enqueues and a
dispatcher loop releases), worker-ai already has a poll loop that pulls running jobs and
submits one decoupled chunk per job per cycle. So this module wires the **pull** ops:

- ``poll_and_run`` iterates owners **round-robin** (WFQ) instead of strict created_at, so a
  new owner's jobs interleave with one owner's giant job rather than queueing behind it.
- before submitting a chapter's decoupled chunk, the runner ``try_acquire_chunk``s a slot
  keyed by the owner; at cap → the chunk is deferred to a later poll (the slot frees when an
  in-flight chunk finalizes). This bounds **in-flight LLM concurrency per owner** — the
  decoupled consumer drives many chunks at once, so without the cap one owner with many
  running projects could saturate the provider.
- the lease is released at the per-chunk TERMINAL — the success chokepoint
  (``llm_extract_consumer._persist_chunk``, same process) reads the token back out of
  ``resume_state`` and releases it. The lease TTL + periodic ``reclaim`` backstop any
  terminal path (poison/crash/permanent-fail) that doesn't reach the fast-path release.

Why the token rides in ``resume_state`` (not recomputed deterministically like translation):
the PULL ``acquire`` returns an opaque ``owner:seq`` token, and ``resume_state`` is the blob
that already survives submit→finalize and is loaded by the consumer — so stashing the
returned token there is the natural carrier. No cross-process recomputation is needed
(the consumer runs in the *same* worker-ai process as the poll loop).

Env-gated (matches ``runner._decouple_enabled`` — os.environ, not the pydantic settings, so
the runner + consumer stay coherent on the same ``P5_SCHED_ENABLED``). Default off ⇒ the
legacy created_at-order / no-cap path is the fallback.

NOTE: PULL ``acquire`` enforces only the per-owner cap, not the global budget (the budget is
a PUSH-dispatch feature). For knowledge the per-owner cap is the noisy-neighbor lever; a
global budget would need a separate accounting pass — deferred until cap proves insufficient.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from loreweave_jobs import FairScheduler

log = logging.getLogger(__name__)

LANE_EXTRACTION = "knowledge:extraction"

_sched: Optional[FairScheduler] = None


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes")


def enabled() -> bool:
    """P5 kill-switch (default off). Read from os.environ to match ``_decouple_enabled``."""
    return _truthy(os.environ.get("P5_SCHED_ENABLED", ""))


def _owner_cap() -> int:
    try:
        return max(1, int(os.environ.get("P5_OWNER_CAP", "5")))
    except ValueError:
        return 5


def _lease_ttl_ms() -> int:
    try:
        return max(1000, int(os.environ.get("P5_LEASE_TTL_MS", "3600000")))
    except ValueError:
        return 3_600_000


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://redis:6379")


def get_scheduler() -> FairScheduler:
    global _sched
    if _sched is None:
        _sched = FairScheduler(
            _redis_url(),
            owner_cap=_owner_cap(),
            lease_ttl_ms=_lease_ttl_ms(),
        )
    return _sched


async def try_acquire_chunk(user_id) -> tuple[bool, Optional[str]]:
    """Claim a per-owner in-flight slot for ``user_id`` before submitting a decoupled chunk.

    Returns ``(allowed, token)``:
      - P5 off ⇒ ``(True, None)`` — no gating, no lease (back-compat).
      - owner under cap ⇒ ``(True, token)`` — caller stashes ``token`` in resume_state and
        the consumer releases it at the chunk terminal.
      - owner at cap ⇒ ``(False, None)`` — caller defers this chunk to a later poll.

    Best-effort fail-OPEN: a redis blip returns ``(True, None)`` so a transient outage degrades
    to the legacy unbounded path rather than wedging extraction (the cap is a fairness knob,
    not a correctness gate)."""
    if not enabled():
        return True, None
    try:
        token = await get_scheduler().acquire(LANE_EXTRACTION, str(user_id), cap=_owner_cap())
    except Exception:  # noqa: BLE001 — fail open; fairness must not block extraction
        log.warning("P5: acquire failed — proceeding un-capped (fail-open)", exc_info=True)
        return True, None
    if token is None:
        return False, None
    return True, token


async def release_chunk(user_id, token: Optional[str]) -> None:
    """Release a chunk's WFQ slot at its terminal. No-op when P5 is off or the token/owner is
    absent (a chunk submitted while P5 was off carries no token). Idempotent (double-release
    returns False); the lease TTL + ``reclaim`` backstop any path that misses this."""
    if not enabled() or not token or not user_id:
        return
    try:
        await get_scheduler().release(LANE_EXTRACTION, str(user_id), token)
    except Exception:  # noqa: BLE001 — best-effort; the lease TTL is the backstop
        log.warning("P5: chunk lease release failed (lease TTL will reclaim)", exc_info=True)


async def reclaim() -> int:
    """Periodic crash backstop — drop expired leases + recompute the total + re-arm the ring.
    No-op (returns 0) when P5 is off."""
    if not enabled():
        return 0
    try:
        return await get_scheduler().reclaim_expired(LANE_EXTRACTION)
    except Exception:  # noqa: BLE001
        log.warning("P5: reclaim failed (will retry next cycle)", exc_info=True)
        return 0


def round_robin_by_owner(jobs: list) -> list:
    """WFQ ordering for the poll loop: interleave jobs across owners (``user_id``) instead of
    strict created_at, preserving created_at order *within* each owner. So owner A's [a1,a2,a3]
    and owner B's [b1] dispatch as [a1, b1, a2, a3] — B's job isn't stuck behind all of A's.

    Stable: owners are ringed in first-appearance (created_at) order, so the earliest-waiting
    owner still leads each pass. No-op shape when P5 is off (caller keeps created_at order)."""
    if not jobs:
        return jobs
    buckets: dict[str, list] = {}
    order: list[str] = []
    for j in jobs:
        key = str(j.user_id)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(j)
    out: list = []
    while any(buckets[k] for k in order):
        for k in order:
            if buckets[k]:
                out.append(buckets[k].pop(0))
    return out
