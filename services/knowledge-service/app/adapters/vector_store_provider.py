"""Where a `VectorStore` actually comes from (plan T25a).

**This is the piece Phase 3 never had.** T22 built the image, T23 the adapter, T24 the
dual-write store — and nothing constructed any of them. A `grep` for their constructors
outside `app/adapters/` returned nothing, so ~1200 lines of tested code executed only in
tests, and `vector_dual_write_total{outcome="secondary_failed"}` — the gate that is supposed
to authorise the T25 cutover — sat at zero because no write ever reached it. A gate reading
zero because nothing is wired looks exactly like a gate reading zero because nothing failed.

── WRITES FIRST, READS LATER. THAT IS WHAT DUAL-WRITE MEANS ──────────────────────────────
This wires the WRITE path only. Reads keep going to Neo4j through the existing repo calls,
because that is precisely the dual-write contract: write both, read the primary, compare.
Swapping reads is the cutover itself (T25), and it cannot honestly happen until the
secondary has been receiving writes long enough for the counter to mean something.

There is a second reason the read swap is not bundled here, found by trying: the semantic
read path hands its hits to `passage_to_hit`, which is **shared with the CJK lexical leg**.
That leg is not a vector search and will never come through this port, so changing the
shared hit shape to the port's `VectorHit` would rewrite a retrieval path this migration has
no business touching. The read cutover needs its own task and its own evidence.

── DEFAULT OFF, AND OFF MEANS BYTE-IDENTICAL ─────────────────────────────────────────────
With `KNOWLEDGE_VECTOR_DB_URL` unset the factory returns a plain `Neo4jVectorStore`: the
same repo functions the call sites used before, reached through one extra method call. No
second database, no dual write, no new failure mode. Turning the migration on is an
explicit act of configuration, which is the only way a self-hoster's upgrade stays boring.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.db.neo4j_helpers import CypherSession
from app.ports.vector_store import VectorStore

logger = logging.getLogger(__name__)

__all__ = ["get_vector_store", "reset_vector_store_pool"]

_pool = None


async def _vector_pool():
    """Lazily open the pool for the vector Postgres, once per process.

    Lazy rather than at startup because the whole point of the default-off design is that a
    deployment without `KNOWLEDGE_VECTOR_DB_URL` never touches a second database — and a
    pool created eagerly at boot would make the service's startup depend on a database that
    the migration has not reached yet.
    """
    global _pool
    if _pool is None:
        import asyncpg

        from app.adapters.pg_vector_store import ensure_vector_schema

        _pool = await asyncpg.create_pool(
            settings.knowledge_vector_db_url, min_size=1, max_size=5, command_timeout=30,
        )
        await ensure_vector_schema(_pool)
        logger.info("T25a: vector-store secondary connected and schema ensured")
    return _pool


async def reset_vector_store_pool() -> None:
    """Close the pool. For tests and shutdown — a module-level pool that outlives its event
    loop is the classic way an async test suite starts failing in unrelated places."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_vector_store(session: CypherSession) -> VectorStore:
    """The composition root. Neo4j alone by default; dual-write when configured.

    Takes the caller's Neo4j session rather than opening its own: the write sites are
    already inside a session (often inside a larger unit of work), and a store that opened a
    second one would put the vector write outside the transaction its caller believes it is
    in.
    """
    from app.adapters.neo4j_vector_store import Neo4jVectorStore

    primary = Neo4jVectorStore(session)
    dsn = getattr(settings, "knowledge_vector_db_url", "")
    if not dsn:
        return primary

    from app.adapters.dual_write_vector_store import DualWriteVectorStore
    from app.adapters.pg_vector_store import PgVectorStore

    async def entity_exists(user_id: str, entity_id: str) -> bool:
        """The oracle `PgVectorStore` refuses to guess without (T23).

        Neo4j is asked, because that is where the entity lives — the vector Postgres holds
        embeddings and cannot see a delete that happened between embedding and write. This
        is the composition root precisely because it is the only layer that can see both.
        """
        from app.db.neo4j_repos.entities import get_entity

        # `get_entity` is the user-scoped lookup, NOT `get_entity_by_id_any_owner`. The
        # oracle decides whether to write a vector for this caller's entity, so an
        # any-owner read would let one tenant's write be authorised by another's row.
        return await get_entity(session, user_id=user_id, canonical_id=entity_id) is not None

    secondary = PgVectorStore(await _vector_pool(), entity_exists=entity_exists)
    return DualWriteVectorStore(
        primary,
        secondary,
        shadow_read_rate=settings.knowledge_vector_shadow_read_rate,
    )
