"""P5 fair-scheduling wiring for lore-enrichment (per-owner concurrent-JOB cap).

Lore-enrichment runs each enrichment job SYNCHRONOUSLY in the `POST /jobs` request
handler (gaps processed sequentially in-process) — there is NO per-unit worker queue to
WFQ-dispatch like translation/knowledge. So the noisy-neighbor lever that fits is a
per-owner cap on **concurrent jobs**: the handler `try_acquire_job`s a slot (lane
`lore-enrichment:job`, owner=user_id) before running `run_job` and `release_job`s it in a
`finally`; at cap the handler returns 429 instead of letting one owner saturate the
provider with many simultaneous enrichment runs.

PULL `acquire` enforces only the per-owner cap (the global budget is a PUSH-dispatch
feature). The acquired token is a local var in the handler (the whole job runs in one
call), so it needs no cross-process carrier — released in `finally`. The lease TTL is the
crash-leak backstop (must exceed the longest job runtime); the `finally` release is the
fast path.

Gated on ``settings.p5_sched_enabled`` (default off → no cap). Fail-OPEN on a redis blip
— fairness must never wedge a legitimate enrichment job.
"""

from __future__ import annotations

import logging
from typing import Optional

from loreweave_jobs import FairScheduler

from app.config import settings

log = logging.getLogger("lore_enrichment.fair_sched")

LANE_JOB = "lore-enrichment:job"

_sched: Optional[FairScheduler] = None


def enabled() -> bool:
    return bool(settings.p5_sched_enabled)


def get_scheduler() -> FairScheduler:
    global _sched
    if _sched is None:
        _sched = FairScheduler(
            settings.redis_url,
            owner_cap=settings.p5_owner_cap,
            lease_ttl_ms=settings.p5_lease_ttl_ms,
        )
    return _sched


async def try_acquire_job(user_id) -> tuple[bool, Optional[str]]:
    """Claim a per-owner concurrent-job slot for ``user_id`` before running a job.

    Returns ``(allowed, token)``:
      - P5 off ⇒ ``(True, None)`` — no cap (back-compat).
      - owner under cap ⇒ ``(True, token)`` — caller releases ``token`` when the job ends.
      - owner at cap ⇒ ``(False, None)`` — caller returns 429.

    Fail-OPEN: a redis blip returns ``(True, None)`` so a transient outage degrades to the
    un-capped path rather than rejecting a legitimate job (fairness ≠ correctness gate)."""
    if not enabled():
        return True, None
    try:
        token = await get_scheduler().acquire(LANE_JOB, str(user_id), cap=settings.p5_owner_cap)
    except Exception:  # noqa: BLE001 — fail open
        log.warning("P5: acquire failed — proceeding un-capped (fail-open)", exc_info=True)
        return True, None
    if token is None:
        return False, None
    return True, token


async def release_job(user_id, token: Optional[str]) -> None:
    """Release a job's concurrency slot when it ends. No-op when off / token absent.
    Idempotent (double-release returns False); the lease TTL backstops a crash before
    the `finally`."""
    if not enabled() or not token or not user_id:
        return
    try:
        await get_scheduler().release(LANE_JOB, str(user_id), token)
    except Exception:  # noqa: BLE001 — best-effort; the lease TTL is the backstop
        log.warning("P5: job lease release failed (lease TTL will reclaim)", exc_info=True)
