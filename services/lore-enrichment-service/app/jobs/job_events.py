"""Unified Job Control Plane P1 — shared constants + helpers for emit_job_event.

lore-enrichment has TWO job-bearing tables wired to the control plane:
  * ``enrichment_job``          — the C8 gap-fill state-machine job (kind ``enrichment_job``)
  * ``enrichment_compose_task`` — the one-shot compose task (kind is the task's own
                                  ``kind`` value: ``profile_suggest`` / ``intent_resolve``)

Both emit a :class:`loreweave_jobs.JobEvent` into ``outbox_events`` (aggregate_type=
``jobs``) on the SAME conn as the status write, so the event commits atomically with the
status change (transactional outbox, H1). worker-infra relays it to
``loreweave:events:jobs``.

The ``enrichment_job`` C8 lifecycle carries an internal ``estimating`` state that is NOT
in the canonical :class:`loreweave_jobs.JobStatus` vocabulary (pending/running/paused/
cancelling/completed/failed/cancelled). Emitting it would raise inside the status-change
tx and roll the legitimate write back, so :func:`canonical_status` maps it to ``None`` —
the caller SKIPS the emit for that transient state (the next real transition,
``running``, is emitted). Every other C8 state maps 1:1 to a canonical value.
"""

from __future__ import annotations

from typing import Any

#: The service id stamped on every emitted JobEvent (Postgres DB ``lore_enrichment``).
JOB_SERVICE = "lore_enrichment"

#: The ``kind`` for the C8 gap-fill ``enrichment_job`` table. Compose tasks instead use
#: their own row ``kind`` (profile_suggest / intent_resolve).
JOB_KIND = "enrichment_job"

#: C8 status → canonical JobStatus value. ``estimating`` is a transient internal state
#: with no canonical equivalent → None (the caller skips the emit; the next ``running``
#: transition carries the event). All others are 1:1.
_STATUS_MAP = {
    "pending": "pending",
    "estimating": None,  # transient internal state — skip (not a canonical JobStatus)
    "running": "running",
    "paused": "paused",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}


def canonical_status(status: str) -> str | None:
    """Map a persisted job status to its canonical JobStatus value, or None when it has
    no canonical equivalent (``estimating``) and the emit must be skipped. An UNKNOWN
    status passes through verbatim so the SDK's own ``JobStatus(...)`` validation is the
    single source of truth (a genuinely-bad value still fails loud)."""
    return _STATUS_MAP.get(status, status)


def job_error(message: str | None) -> dict[str, str] | None:
    """Map a failed job's ``error_message`` to the canonical JobEvent error shape, or
    None when there is no error text."""
    if not message:
        return None
    return {"code": "error", "message": str(message)}


__all__ = ["JOB_SERVICE", "JOB_KIND", "canonical_status", "job_error"]
