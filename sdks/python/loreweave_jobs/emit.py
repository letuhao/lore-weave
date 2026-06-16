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

# Common service-native status aliases → canonical JobStatus. A producer SHOULD map its
# own native status before calling (campaign/knowledge do), but this is the SDK-level
# safety net: an UNMAPPED native must NEVER reach ``JobStatus(...)`` and raise a ValueError
# inside the producer's status-change tx — that would roll back a legitimate transition
# (D-JOBS-EMIT-STATUS-PASSTHROUGH-ROLLBACK). Map what we recognize; skip the rest.
_STATUS_ALIASES: dict[str, JobStatus] = {
    "created": JobStatus.PENDING,
    "queued": JobStatus.PENDING,
    "waiting": JobStatus.PENDING,
    "in_progress": JobStatus.RUNNING,
    "processing": JobStatus.RUNNING,
    "active": JobStatus.RUNNING,
    "started": JobStatus.RUNNING,
    "suspended": JobStatus.PAUSED,
    "stopping": JobStatus.CANCELLING,
    "canceling": JobStatus.CANCELLING,
    "succeeded": JobStatus.COMPLETED,
    "success": JobStatus.COMPLETED,
    "done": JobStatus.COMPLETED,
    "error": JobStatus.FAILED,
    "errored": JobStatus.FAILED,
    "canceled": JobStatus.CANCELLED,
}


# Monotonic in-process counter of emits SKIPPED due to an unmappable status. Dependency-
# free (the SDK pulls in no metrics lib); a consuming service can surface it on its existing
# /metrics or /health via ``skipped_emit_total()``. A non-zero, growing value means a
# producer is repeatedly passing a status that is neither canonical nor in _STATUS_ALIASES
# — i.e. the silent-skip is masking a real producer bug; add the missing mapping.
_skipped_emit_total = 0


def skipped_emit_total() -> int:
    """Cumulative count (this process) of emits skipped because the status was unmappable.
    Surface this from a service's metrics/health endpoint to detect a producer that is
    systematically emitting an unmapped status (the skip is otherwise log-only)."""
    return _skipped_emit_total


def _coerce_status(status: "JobStatus | str") -> Optional[JobStatus]:
    """Coerce a producer-supplied status to a canonical ``JobStatus``, or ``None`` when it
    can't be mapped. ``None`` signals the caller to SKIP the emit instead of raising inside
    the producer's status-change tx — raising would roll back a legitimate transition
    (D-JOBS-EMIT-STATUS-PASSTHROUGH-ROLLBACK; the projection's reconcile sweep backstops a
    skipped event)."""
    if isinstance(status, JobStatus):
        return status
    raw = str(status)
    try:
        return JobStatus(raw)
    except ValueError:
        # Case-insensitive canonical (e.g. "RUNNING") before the native-alias map.
        norm = raw.strip().lower()
        try:
            return JobStatus(norm)
        except ValueError:
            return _STATUS_ALIASES.get(norm)


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

    ``status`` is coerced to a canonical ``JobStatus`` (a ``JobStatus``, a canonical string,
    or a recognized native alias). An UNMAPPABLE status is SKIPPED (logged, no emit, no
    raise) so it can never roll back the producer's status-change tx — D-JOBS-EMIT-STATUS-
    PASSTHROUGH-ROLLBACK; the reconcile sweep backstops the skipped projection update.

    ``aggregate_id`` is the domain ``job_id`` and **MUST be UUID-coercible by Postgres**
    (the ``outbox_events.aggregate_id`` column is ``uuid``). A service whose domain job id
    is NOT a UUID would have this INSERT raise inside the status-change tx and roll the
    whole tx back — so such a service must either map its id to a UUID first or use
    ``emit_job_event_safe`` (best-effort). All P1-migrated services use UUID job ids;
    verify before wiring a new one. ``event_type`` is ``job.<status>``. Dedup key
    downstream is ``(service, job_id, status)``."""
    coerced = _coerce_status(status)
    if coerced is None:
        # Unmappable native status — SKIP the emit (don't raise) so the producer's
        # status-change tx still commits. D-JOBS-EMIT-STATUS-PASSTHROUGH-ROLLBACK: a
        # raising ``JobStatus(...)`` here would roll back a legitimate transition. The
        # projection's reconcile sweep is the durability backstop for the skipped event.
        # Count it (skipped_emit_total) + emit a stable, greppable marker so a systematic
        # producer bug is alertable, not just buried in logs.
        global _skipped_emit_total
        _skipped_emit_total += 1
        log.warning(
            "[EMIT_STATUS_SKIPPED] emit_job_event: unmappable status %r (service=%s job=%s "
            "kind=%s) — skipping emit so the status-change tx still commits (reconcile-sweep "
            "backstop applies; cumulative skipped=%d)",
            status, service, job_id, kind, _skipped_emit_total,
        )
        return
    status_value = coerced.value
    event = JobEvent(
        service=service,
        job_id=str(job_id),
        owner_user_id=str(owner_user_id),
        kind=kind,
        status=coerced,
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
