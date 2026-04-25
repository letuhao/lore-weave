"""C17 — one-shot backfill for entity_alias_map.

Walks every non-archived :Entity node and writes alias-map rows for
each alias != canonical_name (the entity's own canonical_name is
implicit via its id and never needs a redirect row).

Idempotent: re-runs are no-ops via ``EntityAliasMapRepo.bulk_backfill``'s
ON CONFLICT DO NOTHING. Safe to interrupt and resume.

Required because pre-C17 ``merge_entities`` calls didn't write to the
alias-map table — those merges' redirect rows must be reconstructed
from the existing ``:Entity.aliases`` arrays. Run-once post-deploy:

    python -m app.db.migrations.backfill_entity_alias_map

Output: prints ``inserted=N skipped_canonical=M total_entities=K``
to stdout. Logs any per-entity exceptions but doesn't abort the
sweep — backfill is best-effort by design.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.canonical import canonicalize_entity_name
from app.db.repositories.entity_alias_map import EntityAliasMapRepo

logger = logging.getLogger(__name__)

__all__ = ["run_backfill", "BackfillResult"]


# Walk every non-archived entity. archived_at IS NULL filter prevents
# stale-archive aliases from redirecting future extractions onto a
# tombstoned entity.
_BACKFILL_LIST_ENTITIES_CYPHER = """
MATCH (e:Entity)
WHERE e.archived_at IS NULL
RETURN e.user_id        AS user_id,
       e.project_id     AS project_id,
       e.kind           AS kind,
       e.canonical_name AS canonical_name,
       e.aliases        AS aliases,
       e.id             AS target_entity_id
"""


class BackfillResult:
    """Plain stats holder — not a Pydantic model because the only
    consumer is the CLI shim and the unit tests, both of which want
    direct attribute access."""

    def __init__(self) -> None:
        self.total_entities = 0
        self.inserted = 0
        self.skipped_canonical = 0   # alias canonicalizes to entity's own canonical_name
        self.skipped_empty = 0       # alias canonicalizes to empty string
        self.errored_entities = 0    # per-entity exceptions (logged + counted)

    def __repr__(self) -> str:  # pragma: no cover (debug aid only)
        return (
            f"BackfillResult(total_entities={self.total_entities}, "
            f"inserted={self.inserted}, "
            f"skipped_canonical={self.skipped_canonical}, "
            f"skipped_empty={self.skipped_empty}, "
            f"errored_entities={self.errored_entities})"
        )


async def run_backfill(
    repo: EntityAliasMapRepo,
    session: CypherSession,
) -> BackfillResult:
    """Walk Neo4j entities, write alias-map rows in one bulk insert.

    The repo + session are passed in (rather than constructed here)
    so unit tests can swap fakes. The CLI shim at the bottom of this
    module handles real-pool / real-Neo4j-session construction.
    """
    result = BackfillResult()
    rows_to_insert: list[tuple[UUID, str, str, str, str]] = []

    # Cross-tenant scan: backfill is a one-shot ops-triggered migration
    # that explicitly walks every user's entities. Bypassing run_read
    # (which enforces per-user $user_id binding) is intentional and
    # documented — an operator initiates this; no user request flows
    # through the helper. The query is read-only.
    cypher_result = await session.run(_BACKFILL_LIST_ENTITIES_CYPHER)
    async for record in cypher_result:
        result.total_entities += 1
        try:
            user_id = UUID(record["user_id"])
        except (TypeError, ValueError, KeyError):
            result.errored_entities += 1
            logger.warning(
                "C17 backfill: entity has invalid user_id, skipping: %r",
                record.get("user_id"),
            )
            continue
        project_scope = record["project_id"] or "global"
        kind = record["kind"]
        canonical_name = record["canonical_name"]
        target_id = record["target_entity_id"]
        aliases: list[Any] = record["aliases"] or []
        for alias in aliases:
            if not isinstance(alias, str):
                continue
            ca = canonicalize_entity_name(alias)
            if not ca:
                result.skipped_empty += 1
                continue
            if ca == canonical_name:
                # Entity's own canonical name — redirect is implicit
                # via the entity's id; no row needed.
                result.skipped_canonical += 1
                continue
            rows_to_insert.append(
                (user_id, project_scope, kind, ca, target_id),
            )

    if rows_to_insert:
        result.inserted = await repo.bulk_backfill(rows_to_insert)
    return result


# CLI entry point — invoked via `python -m app.db.migrations.backfill_entity_alias_map`.
async def _cli_main() -> None:  # pragma: no cover (integration-only)
    """Production entry point. Constructs real pool + Neo4j session
    from app.config; logs the BackfillResult to stdout. Not unit-
    tested because it touches real I/O — coverage is on run_backfill.
    """
    from app.config import settings  # noqa: F401  (init validation)
    from app.db.neo4j import get_neo4j_driver, neo4j_session
    from app.db.pool import get_knowledge_pool, init_knowledge_pool

    logging.basicConfig(level=logging.INFO)
    await init_knowledge_pool()
    # Ensure driver lifecycle for the session context manager.
    get_neo4j_driver()
    pool = get_knowledge_pool()
    repo = EntityAliasMapRepo(pool)
    async with neo4j_session() as session:
        result = await run_backfill(repo, session)
    logger.info(
        "C17 backfill complete: total=%d inserted=%d skipped_canonical=%d "
        "skipped_empty=%d errored=%d",
        result.total_entities, result.inserted, result.skipped_canonical,
        result.skipped_empty, result.errored_entities,
    )


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_cli_main())
