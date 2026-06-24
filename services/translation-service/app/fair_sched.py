"""P5 fair-scheduling wiring for translation (the PUSH substrate).

Lane ``translation:chapter``: the coordinator ENQUEUEs per-chapter units into the
per-owner WFQ instead of publishing them all; this module's dispatcher loop releases
them round-robin (≤ ``p5_owner_cap`` in-flight per owner, ≤ ``p5_global_budget`` total)
and publishes ``translation.chapter`` carrying the lease token; the chapter worker
releases the lease on terminal. Stops one owner's giant job from monopolizing the fleet.

Gated on ``settings.p5_sched_enabled`` (default off → legacy direct-publish path).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from loreweave_jobs import FairScheduler

from .config import settings

log = logging.getLogger(__name__)

LANE_CHAPTER = "translation:chapter"

_sched: Optional[FairScheduler] = None


def chapter_token(job_id, chapter_id) -> str:
    """Deterministic per-chapter lease token. Computable from data in scope at BOTH
    dispatch (coordinator) and finalize (sync chapter_worker OR the decoupled
    llm_terminal_consumer) — so the slot is released by the chapter that actually
    finished its LLM work, in whichever process finalizes it."""
    return f"{job_id}:{chapter_id}"


def get_scheduler() -> FairScheduler:
    global _sched
    if _sched is None:
        _sched = FairScheduler(
            settings.redis_url,
            owner_cap=settings.p5_owner_cap,
            global_budget=settings.p5_global_budget,
            lease_ttl_ms=settings.p5_lease_ttl_ms,
        )
    return _sched


async def release_chapter_lease(msg: dict) -> None:
    """Release a chapter unit's WFQ slot at its per-chapter TERMINAL. Called from
    ``_check_job_completion`` (the per-chapter terminal chokepoint — success for both
    the sync and decoupled pipelines via ``_finalize_chapter``, plus the failure paths)
    and from the worker's abandon branches. Uses the DETERMINISTIC token
    (``job_id:chapter_id``) so it frees the exact slot the coordinator leased, even when
    the finalize runs in a different process than the dispatch (the decoupled consumer
    runs in the API container).

    Holding the lease from dispatch until this terminal is what makes the per-owner cap
    bound real in-flight LLM concurrency in the decoupled path (not just submit-rate).

    No-op when P5 is off or the message lacks job_id/chapter_id/owner — so a flag flip
    mid-flight can never crash a worker. Idempotent (a double-release returns False); the
    lease TTL backstops any terminal path that doesn't reach a release site."""
    if not settings.p5_sched_enabled:
        return
    job_id = msg.get("job_id")
    chapter_id = msg.get("chapter_id")
    owner = msg.get("user_id")
    if not job_id or not chapter_id or not owner:
        return
    try:
        await get_scheduler().release(LANE_CHAPTER, str(owner), chapter_token(job_id, chapter_id))
    except Exception:  # noqa: BLE001 — best-effort; the lease TTL is the backstop
        log.warning("P5: chapter lease release failed (lease TTL will reclaim)", exc_info=True)


async def run_dispatcher(publish: Callable[[str, dict], Awaitable[None]]) -> None:
    """Dispatcher loop: round-robin release ready chapter units → publish
    ``translation.chapter`` (carrying the lease token). Multiple worker replicas may run
    this concurrently — ``dispatch`` is atomic in Redis, so the cap/budget hold across all
    of them (no leader election needed). Periodically reclaims expired leases."""
    sched = get_scheduler()
    log.info(
        "P5 dispatcher started (lane=%s cap=%d budget=%d interval=%.2fs)",
        LANE_CHAPTER, settings.p5_owner_cap, settings.p5_global_budget,
        settings.p5_dispatch_interval_s,
    )
    last_reclaim = 0.0
    while True:
        try:
            released = await sched.dispatch(LANE_CHAPTER)
            for token, unit in released:
                await publish("translation.chapter", {**unit, "_p5_token": token})

            now = time.monotonic()
            if now - last_reclaim >= settings.p5_reclaim_interval_s:
                await sched.reclaim_expired(LANE_CHAPTER)
                last_reclaim = now

            # Drain fast while there's work; sleep only when a tick released nothing
            # (all owners idle or at cap — a release/enqueue re-arms within one interval).
            if not released:
                await asyncio.sleep(settings.p5_dispatch_interval_s)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a transient redis blip must not kill the loop
            log.warning("P5 dispatcher tick failed (retrying)", exc_info=True)
            await asyncio.sleep(settings.p5_dispatch_interval_s)
