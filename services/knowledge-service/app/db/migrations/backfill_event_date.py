"""C18 — one-shot backfill for event_date_iso.

Walks every :Event node with ``time_cue IS NOT NULL AND event_date_iso
IS NULL`` and runs the existing ``parse_time_cue_to_iso`` parser; if
the parser returns a value, writes it as ``event_date_iso``.

Idempotent: re-runs skip rows where ``event_date_iso`` is already set
(via the WHERE filter). Safe to interrupt and resume.

Required because pre-C18 :Event nodes have no ``event_date_iso``
property — the LLM extractor's ``event_date`` JSON field was added in
C18 too. Backfill recovers structured dates from existing free-text
``time_cue`` strings without re-running the LLM ($).

Run-once post-deploy::

    python -m app.db.migrations.backfill_event_date

Output: prints ``scanned=N parsed=M skipped_unparseable=K`` to stdout.
Best-effort: parsing failures don't abort the sweep.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db.neo4j_helpers import CypherSession
from app.utils.event_date_parser import parse_time_cue_to_iso

logger = logging.getLogger(__name__)

__all__ = ["run_backfill", "BackfillResult"]


# Cross-tenant scan: backfill is operator-triggered, walks every
# user's events. Bypasses run_read's per-user $user_id binding by
# using session.run directly (same pattern as the C17 alias-map
# backfill — explicit cross-tenant intent, read-only sweep).
_LIST_EVENTS_NEEDING_DATE_CYPHER = """
MATCH (e:Event)
WHERE e.time_cue IS NOT NULL
  AND e.event_date_iso IS NULL
  AND e.archived_at IS NULL
RETURN e.id AS id, e.time_cue AS time_cue
"""

# Update by event id (no user_id filter — backfill is cross-tenant
# and the precondition WHERE in the SELECT already filtered out
# rows that don't need the update).
_UPDATE_EVENT_DATE_CYPHER = """
MATCH (e:Event {id: $id})
SET e.event_date_iso = $event_date_iso,
    e.updated_at = datetime()
"""


class BackfillResult:
    """Plain stats holder — direct attribute access from CLI + tests."""

    def __init__(self) -> None:
        self.scanned = 0
        self.parsed = 0
        self.skipped_unparseable = 0
        self.errored = 0  # per-row exceptions during UPDATE

    def __repr__(self) -> str:  # pragma: no cover (debug aid only)
        return (
            f"BackfillResult(scanned={self.scanned}, "
            f"parsed={self.parsed}, "
            f"skipped_unparseable={self.skipped_unparseable}, "
            f"errored={self.errored})"
        )


async def run_backfill(session: CypherSession) -> BackfillResult:
    """Walk events with parseable time_cue, write event_date_iso.

    The session is passed in so unit tests can swap a fake. CLI shim
    constructs the real Neo4j session.
    """
    result = BackfillResult()
    cypher_result = await session.run(_LIST_EVENTS_NEEDING_DATE_CYPHER)
    rows: list[tuple[str, Any]] = []
    async for record in cypher_result:
        result.scanned += 1
        rows.append((record["id"], record["time_cue"]))

    for event_id_, time_cue in rows:
        parsed = parse_time_cue_to_iso(time_cue)
        if parsed is None:
            result.skipped_unparseable += 1
            continue
        try:
            await session.run(
                _UPDATE_EVENT_DATE_CYPHER,
                id=event_id_,
                event_date_iso=parsed,
            )
            result.parsed += 1
        except Exception:
            result.errored += 1
            logger.warning(
                "C18 backfill: UPDATE failed for event_id=%s parsed=%s",
                event_id_, parsed,
                exc_info=True,
            )

    return result


async def _cli_main() -> None:  # pragma: no cover (integration-only)
    """Production entry point. Not unit-tested — coverage lives in
    run_backfill."""
    from app.config import settings  # noqa: F401  (init validation)
    from app.db.neo4j import get_neo4j_driver, neo4j_session

    logging.basicConfig(level=logging.INFO)
    get_neo4j_driver()
    async with neo4j_session() as session:
        result = await run_backfill(session)
    logger.info(
        "C18 backfill complete: scanned=%d parsed=%d "
        "skipped_unparseable=%d errored=%d",
        result.scanned, result.parsed,
        result.skipped_unparseable, result.errored,
    )


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_cli_main())
