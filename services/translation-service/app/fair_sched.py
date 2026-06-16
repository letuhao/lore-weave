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
    """Release a chapter unit's WFQ lease on terminal. No-op when P5 is off or the
    message predates P5 (no token) — so a flag flip mid-flight can never crash a worker;
    the lease TTL backstops a missed release.

    NOTE (decoupled-mode semantics — D-P5-DECOUPLED-LLM-CAP): in the default DECOUPLED
    translate path the chapter worker SUBMITS the LLM job and acks in ~50ms (the real
    translation finalizes async via the llm_terminal_consumer), so releasing here frees
    the slot at SUBMIT time. The WFQ **dispatch fairness** still holds end-to-end (a new
    owner's chapters round-robin-interleave instead of queueing behind a giant job, and
    the AMQP queue is never flooded) — but the per-owner **cap** then bounds submit-
    concurrency, not in-flight LLM concurrency. A true LLM cap needs the release moved to
    the per-chapter finalize point (thread the lease token through resume_state → terminal
    event → finalize). Tracked for the cap-tightening follow-up."""
    if not settings.p5_sched_enabled:
        return
    token = msg.get("_p5_token")
    owner = msg.get("user_id")
    if not token or not owner:
        return
    try:
        await get_scheduler().release(LANE_CHAPTER, str(owner), str(token))
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
