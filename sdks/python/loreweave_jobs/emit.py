"""``emit_job_event`` — write a job-lifecycle event to the producer's transactional
outbox (Unified Job Control Plane, L2 / consistency model H1).

The event row is inserted into the producing service's ``outbox_events`` table in the
**SAME transaction** as the job-row status change, so it is relayed exactly-once by
worker-infra's outbox relay to ``loreweave:events:jobs`` (aggregate_type=``jobs``) — NOT a
fire-and-forget publish. This is the load-bearing correctness decision: a dropped event
would leave a job stuck "running" forever in the GUI.

The connection is **duck-typed** (anything with an ``async execute(sql, *args)`` — an
asyncpg ``Connection`` inside a tx, or a ``Pool`` for the best-effort variant), so this
module has no asyncpg import and stays dependency-free.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .contract import JOBS_AGGREGATE_TYPE, JobEvent, JobStatus

log = logging.getLogger(__name__)

# The producer outbox the worker-infra relay polls. aggregate_type=`jobs` → JOBS_STREAM.
_INSERT_OUTBOX = """
INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
VALUES ($1, $2::uuid, $3, $4::jsonb)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_job_event(
    conn: Any,
    *,
    service: str,
    job_id: str,
    owner_user_id: str,
    kind: str,
    status: "JobStatus | str",
    parent_job_id: Optional[str] = None,
    detail_status: Optional[str] = None,
    progress: Optional[dict[str, int]] = None,
    title: Optional[str] = None,
    error: Optional[dict[str, str]] = None,
    model: Optional[str] = None,
    cost_usd: Optional[float] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    params: Optional[dict[str, Any]] = None,
    occurred_at: Optional[str] = None,
) -> None:
    """Insert a job-lifecycle ``JobEvent`` into ``outbox_events`` via ``conn`` (an open
    asyncpg connection/transaction — call this INSIDE the same tx as the status change so
    the two commit atomically; H1). Raises on a DB error so the surrounding tx rolls back
    (the status change must NOT commit without its event — use ``emit_job_event_safe`` for
    a deliberately best-effort callsite).

    ``aggregate_id`` is the domain ``job_id`` and **MUST be UUID-coercible by Postgres**
    (the ``outbox_events.aggregate_id`` column is ``uuid``). A service whose domain job id
    is NOT a UUID would have this INSERT raise inside the status-change tx and roll the
    whole tx back — so such a service must either map its id to a UUID first or use
    ``emit_job_event_safe`` (best-effort). All P1-migrated services use UUID job ids;
    verify before wiring a new one. ``event_type`` is ``job.<status>``. Dedup key
    downstream is ``(service, job_id, status)``."""
    status_value = status.value if isinstance(status, JobStatus) else str(status)
    event = JobEvent(
        service=service,
        job_id=str(job_id),
        owner_user_id=str(owner_user_id),
        kind=kind,
        status=JobStatus(status_value),
        parent_job_id=str(parent_job_id) if parent_job_id else None,
        detail_status=detail_status,
        progress=progress,
        title=title,
        error=error,
        model=model,
        cost_usd=cost_usd,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        params=params,
        occurred_at=occurred_at or _now_iso(),
    )
    await conn.execute(
        _INSERT_OUTBOX,
        JOBS_AGGREGATE_TYPE,
        str(job_id),
        f"job.{status_value}",
        json.dumps(event.to_payload(), default=str),
    )


async def emit_job_event_safe(pool: Any, **kwargs: Any) -> bool:
    """Best-effort variant for a callsite that is NOT inside a tx with the status change
    (e.g. a transition that already committed). Swallows any error and returns False so a
    failed emit can never turn a successful operation into a 500 — the projection's
    reconcile sweep is the durability backstop. Prefer ``emit_job_event`` (in-tx) whenever
    the status change is itself a DB write you control."""
    try:
        await emit_job_event(pool, **kwargs)
        return True
    except Exception:  # noqa: BLE001
        log.warning(
            "emit_job_event_safe: best-effort emit failed for service=%s job=%s status=%s "
            "(reconcile-sweep backstop applies)",
            kwargs.get("service"), kwargs.get("job_id"), kwargs.get("status"),
            exc_info=True,
        )
        return False
