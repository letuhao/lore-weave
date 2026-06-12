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
# Auto-Draft Factory S1 (decision H) — per-chapter knowledge completion, consumed
# by campaign-service's projection (`campaign-collector`) to advance the
# knowledge stage. Distinct from the run-telemetry event above (which learning
# consumes); both ride `loreweave:events:knowledge`.
CHAPTER_EXTRACTED_EVENT = "knowledge.chapter_extracted"
# S3c-2b — per-chapter extraction failure carrying the LLM error_code, consumed
# by campaign-service to auto-pause on LLM_CIRCUIT_OPEN.
CHAPTER_FAILED_EVENT = "knowledge.chapter_failed"


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


async def emit_chapter_extracted(
    executor: _Executor,
    *,
    user_id: str,
    project_id: str,
    book_id: str | None,
    chapter_id: str,
) -> None:
    """Auto-Draft Factory S1 (decision H) — emit `knowledge.chapter_extracted`
    on a chapter's successful extraction, for campaign-service's projection.

    TRANSACTIONAL variant (D-CAMPAIGN-BESTEFFORT-EMIT-REDIS): run on the caller's
    connection INSIDE the cursor-advance transaction so the campaign's load-bearing
    completion event is written iff the chapter's cursor advanced — closing the
    silent-loss window where a failed standalone insert left the cursor advanced
    but no event (→ the campaign stalled `dispatched` forever, since the S3
    stuck-reconcile is the only backstop). Carries the minimal correlation tuple
    (user_id, book_id, chapter_id); `book_id` may be None for a project with no
    linked book (no campaign matches — harmless no-op downstream). aggregate_id =
    chapter_id."""
    await executor.execute(
        """
        INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
        VALUES ('knowledge', $1, $2, $3::jsonb)
        """,
        uuid.UUID(str(chapter_id)),
        CHAPTER_EXTRACTED_EVENT,
        json.dumps(
            {
                "user_id": str(user_id),
                "project_id": str(project_id),
                "book_id": str(book_id) if book_id else None,
                "chapter_id": str(chapter_id),
                "status": "extracted",
            },
            default=str,
        ),
    )


async def emit_chapter_extracted_best_effort(
    executor: _Executor,
    *,
    user_id: str,
    project_id: str,
    book_id: str | None,
    chapter_id: str,
) -> None:
    """Best-effort wrapper — never raises. Used only on the transaction-FALLBACK
    path (when the atomic cursor+run+chapter emit failed and the cursor was advanced
    best-effort): we still try to emit the chapter event so the campaign advances,
    and the S3 stuck-reconcile remains the backstop for the rare residual loss."""
    try:
        await emit_chapter_extracted(
            executor, user_id=user_id, project_id=project_id,
            book_id=book_id, chapter_id=chapter_id,
        )
    except Exception:
        logger.warning(
            "outbox: failed to emit %s for chapter %s (non-fatal — campaign "
            "projection self-heals)",
            CHAPTER_EXTRACTED_EVENT, chapter_id, exc_info=True,
        )


async def emit_chapter_failed_best_effort(
    executor: _Executor,
    *,
    user_id: str,
    project_id: str,
    book_id: str | None,
    chapter_id: str,
    error_code: str,
) -> None:
    """S3c-2b — emit `knowledge.chapter_failed` (error_code) when a chapter's
    extraction fails because the provider's S3a circuit is OPEN, so
    campaign-service auto-pauses. Best-effort: a lost emit just means the campaign
    keeps churning until the breaker self-heals. The caller emits ONLY on
    LLM_CIRCUIT_OPEN (the campaign pauses solely on that code)."""
    try:
        await executor.execute(
            """
            INSERT INTO outbox_events (aggregate_type, aggregate_id, event_type, payload)
            VALUES ('knowledge', $1, $2, $3::jsonb)
            """,
            uuid.UUID(str(chapter_id)),
            CHAPTER_FAILED_EVENT,
            json.dumps(
                {
                    "user_id": str(user_id),
                    "project_id": str(project_id),
                    "book_id": str(book_id) if book_id else None,
                    "chapter_id": str(chapter_id),
                    "error_code": error_code,
                },
                default=str,
            ),
        )
    except Exception:
        logger.warning(
            "outbox: failed to emit %s for chapter %s (non-fatal)",
            CHAPTER_FAILED_EVENT, chapter_id, exc_info=True,
        )
