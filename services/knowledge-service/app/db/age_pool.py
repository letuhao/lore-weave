"""The process-wide AGE connection pool — a `db` concern, not an adapter one.

⚠️ **This lived in `adapters/graph_store_provider` until T54c, and only because that is who
needed it first.** Once `neo4j_session` had to open a repo-layer session against AGE, the
session factory had to import an ADAPTER module to get a connection pool — and
`port-adoption-gate` caught it immediately: its GraphStore-adopter floor rose from 19 to 20 on
an import that touches no store. A number meaning *"modules that adopted the port"* must not
count modules that wanted a database handle.

`graph_store_provider` still owns the decision of WHICH `GraphStore` to build. It no longer
owns the connection pool, which two layers now share.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["age_pool", "close_age_pool", "init_age_pool"]

#: One pool per process, built on first use. Not at import: the DSN is configuration and a
#: module that opens a connection at import time cannot be imported by a test, a script, or a
#: worker that will never touch the graph.
_POOL: Any = None


def age_pool() -> Any:
    """The process AGE pool, or None when no DSN is configured."""
    return _POOL


async def init_age_pool() -> bool:
    """Build the AGE pool from settings. Idempotent; returns True when a pool exists.

    Called from the service lifespan beside `run_neo4j_schema`, so a misconfigured backend
    fails at STARTUP where someone is watching rather than on the first user request.
    """
    global _POOL
    if _POOL is not None:
        return True
    from app.config import settings

    dsn = (settings.knowledge_age_db_url or "").strip()
    if not dsn:
        return False
    from app.db.age_bootstrap import (
        create_age_pool,
        ensure_age_extension,
        ensure_graph,
        graph_name_for,
    )

    _POOL = await create_age_pool(dsn)
    await ensure_age_extension(_POOL)
    async with _POOL.acquire() as conn:
        await ensure_graph(conn, None)          # the shared graph, created if absent
    logger.info("AGE pool ready (graph=%s)", graph_name_for(None))
    return True


async def close_age_pool() -> None:
    """Release the pool. Idempotent, so a lifespan that never opened one can still call it."""
    global _POOL
    if _POOL is not None:
        pool, _POOL = _POOL, None
        await pool.close()
