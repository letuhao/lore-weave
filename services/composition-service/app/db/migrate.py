"""composition-service schema migration (idempotent, single-DDL house style).

M0: no-op placeholder — the service boots with an empty database. M1 fills
`_SCHEMA_SQL` with the §1.2 DDL (composition_work, outline_node, scene_link,
canon_rule, generation_job, outbox_events, structure_template seed) and the
`base_revision_id` column. Like knowledge-service, this is a single idempotent
`CREATE … IF NOT EXISTS` blob applied on every startup — no migration tool.
"""

import logging

import asyncpg

logger = logging.getLogger(__name__)

# M1 will populate this with the §1.2 DDL. Kept as an empty string so the
# run loop below is already wired and M1 is a pure data change.
_SCHEMA_SQL = ""


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Apply the idempotent schema. No-op until M1 lands the DDL."""
    if not _SCHEMA_SQL.strip():
        logger.info("composition migrate: no schema yet (M1 lands §1.2 DDL)")
        return
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)
    logger.info("composition migrate: schema applied")
