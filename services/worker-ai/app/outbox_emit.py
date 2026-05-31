"""Phase B2-A — worker-ai extraction-run outbox emit.

worker-ai shares knowledge-service's Postgres, so it writes run-telemetry
events into the same `outbox_events` table knowledge-service uses for
corrections; worker-infra's relay ships them to `loreweave:events:knowledge`
for learning-service to persist as `extraction_runs` + `config_registry`
(DESIGN §4.1).

TRANSACTIONAL on success/skip: `emit_extraction_run` runs the INSERT on the
**caller's connection** so it commits or rolls back together with the chapter's
cursor-advance — a chapter that advanced the cursor always has a run row, and a
failed insert re-processes the chapter rather than silently dropping the run
(DESIGN Q-runs, kills the §2.4 selection-bias risk).

BEST-EFFORT on the failure path: `emit_extraction_run_best_effort` wraps the
same insert in try/except (the fail path doesn't advance a cursor to ride, and
an emit failure must never mask the real extraction failure).

`outbox_events.id` (uuidv7) becomes the relay's `outbox_id` dedup key;
`aggregate_id` carries the `run_id`.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

logger = logging.getLogger(__name__)

RUN_COMPLETED_EVENT = "knowledge.extraction_run_completed"


class _Executor(Protocol):
    async def execute(self, query: str, *args: Any) -> Any: ...


async def emit_extraction_run(executor: _Executor, payload: dict) -> None:
    """INSERT a run-completed event into outbox_events on `executor`.

    `executor` is an asyncpg Connection (inside a transaction — success/skip
    path) OR a Pool (best-effort wrapper). `payload["run_id"]` becomes the
    event's aggregate_id; the full payload is the event body.
    """
    await executor.execute(
        """
        INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
        VALUES ('knowledge', $1, $2, $3::jsonb)
        """,
        uuid.UUID(str(payload["run_id"])),
        RUN_COMPLETED_EVENT,
        json.dumps(payload, default=str),
    )


async def emit_extraction_run_best_effort(pool: _Executor, payload: dict) -> None:
    """Best-effort variant for the failure path — never raises.

    A lost failure-run only under-counts the rarer failure case; it must not
    turn an extraction failure into a worker crash."""
    try:
        await emit_extraction_run(pool, payload)
    except Exception:
        logger.warning(
            "outbox: failed to emit extraction_run (outcome=%s) for run %s "
            "(non-fatal — run log under-counts a failure)",
            payload.get("outcome"), payload.get("run_id"), exc_info=True,
        )
