"""loreweave_jobs — the shared background-job control-plane SDK (Unified Job
Control Plane, P1).

Three pieces, all imported from here:

- ``contract`` — the canonical job shape every service emits + the projection stores
  (``JobStatus``, ``ControlCap``, ``JobRecord``, ``JobEvent``) + the stream constants.
- ``consumer.BaseTerminalConsumer`` — the genuinely-shared Redis-Streams **transport
  scaffold** (BUSYGROUP-safe group, startup PEL drain, redis-py-8 idle ``TimeoutError``,
  operation pre-filter, bounded-retry-then-poison-ack, sweeper scaffold). A subclass
  supplies only the divergent business logic (``stream``/``group``/``handle``/``sweep_once``).
  This deduplicates the ~12 hand-rolled copies (and the bugs that were copied between them).
- ``emit.emit_job_event`` — write a ``JobEvent`` to the producer's transactional outbox
  (same tx as the job-row status change) → relayed to ``loreweave:events:jobs``.

See ``docs/specs/2026-06-15-unified-job-control-plane.md`` (L0/L2 + invariants H1–H4).
"""

from __future__ import annotations

from .contract import (
    JOBS_AGGREGATE_TYPE,
    JOBS_STREAM,
    TERMINAL,
    TERMINAL_STREAM,
    ControlCap,
    JobEvent,
    JobRecord,
    JobStatus,
)
from .consumer import BaseTerminalConsumer
from .projection_consumer import BaseProjectionConsumer
from .emit import emit_job_event, emit_job_event_safe, skipped_emit_total
from .scheduler import FairScheduler

__all__ = [
    "JobStatus",
    "TERMINAL",
    "ControlCap",
    "JobRecord",
    "JobEvent",
    "JOBS_STREAM",
    "JOBS_AGGREGATE_TYPE",
    "TERMINAL_STREAM",
    "BaseTerminalConsumer",
    "BaseProjectionConsumer",
    "emit_job_event",
    "emit_job_event_safe",
    "skipped_emit_total",
    "FairScheduler",
]
