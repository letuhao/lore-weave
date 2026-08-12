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
from app.metrics import vector_dual_write_total
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

        # Built into a LOCAL, published to `_pool` only once the schema is ensured. The
        # earlier version assigned `_pool` first, so a `create_pool` that succeeded followed
        # by an `ensure_vector_schema` that failed left a CACHED pool whose schema had never
        # been applied — and because the cache is checked with `is None`, every later call
        # returned that pool and skipped the ensure permanently. The failure would surface
        # far away, as a missing table on write.
        pool = await asyncpg.create_pool(
            settings.knowledge_vector_db_url, min_size=1, max_size=5, command_timeout=30,
        )
        try:
            await ensure_vector_schema(pool)
        except Exception:
            # Do not leak the connections on the way out; leaving `_pool` None means the
            # next call retries cleanly.
            await pool.close()
            raise
        _pool = pool
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

    # ⚠️ THE SECONDARY MUST NEVER BE ABLE TO FAIL THE PRIMARY WRITE.
    #
    # `DualWriteVectorStore.upsert` already guarantees that — it swallows a secondary
    # exception and counts `secondary_failed` — but that protection begins only once the
    # store EXISTS. Building it is where the gap was: `_vector_pool()` opens the connection
    # pool lazily, so with the DSN set and the secondary unreachable this line RAISED, the
    # exception propagated out of the composition root, and passage ingestion failed
    # outright. The primary is the system of record and it never got written.
    #
    # Found 2026-08-12 by the OD-2 live run, on the first day the secondary was switched on,
    # by stopping the container and re-driving a write:
    #
    #     socket.gaierror: [Errno -3] Temporary failure in name resolution
    #     (raised out of get_vector_store -> _vector_pool -> asyncpg.create_pool)
    #
    # So a secondary outage is degraded, not propagated: the caller gets the primary-only
    # store it had before the migration. `_pool` stays None, so the NEXT call retries and
    # recovery is automatic — no restart needed.
    #
    # It is counted, not merely logged. Degrading silently would recreate the exact defect
    # `D-T25B-SOAK` exists to prevent: `secondary_failed` sitting at zero because nothing
    # was wired, indistinguishable from zero because nothing failed. Reusing that existing
    # series (rather than minting a new one) means the soak gate ALREADY watches this — an
    # unreachable secondary reds the same check a rejected write does, which is right,
    # because both mean the same thing at cutover: the target is missing rows.
    try:
        pool = await _vector_pool()
    except Exception as exc:  # noqa: BLE001
        for scope in ("passage", "entity"):
            vector_dual_write_total.labels(scope=scope, outcome="secondary_failed").inc()
        logger.error(
            "T25a: vector secondary UNREACHABLE — serving primary-only this call, and the "
            "rows written now will be MISSING at cutover. err=%s", exc,
        )
        return primary

    secondary = PgVectorStore(pool, entity_exists=entity_exists)
    return DualWriteVectorStore(
        primary,
        secondary,
        shadow_read_rate=settings.knowledge_vector_shadow_read_rate,
    )
