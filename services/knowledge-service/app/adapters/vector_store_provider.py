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
from app.db.graph_backend import configured_backend
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


def read_scopes(*, cutover: bool, has_anchor_resolver: bool) -> frozenset[str]:
    """Which scopes the FIRST store in the dual-write pair answers (T25s).

    Extracted so the rule has ONE home. The first cut left it inline and its test recomputed
    the same expression — which agreed with the provider by luck, not by construction: a bite
    that changed the provider left the test green because the test was asserting its own copy.
    That is the "detector fitted to its own example" shape, caught by the bite failing to bite.

    · not cut over      -> Neo4j is first and answers BOTH scopes.
    · cut over          -> Postgres answers passages.
    · cut over + a resolver -> Postgres answers entities too, because `anchor_score` can be
      joined from its authority (§3.3c). Without one it CANNOT be ranked, and serving an
      unranked entity read is not an error — just a quietly worse ordering, which is the §9.1
      failure in a new place.
    """
    if not cutover:
        return frozenset({"passage", "entity"})
    return frozenset({"passage", "entity"}) if has_anchor_resolver else frozenset({"passage"})


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
    read_primary = getattr(settings, "knowledge_vector_read_primary", "neo4j")
    if read_primary not in ("neo4j", "postgres"):
        # A typo here is a silent revert to Neo4j — the operator believes the cutover
        # happened and the metrics agree with them, because nothing changed.
        raise ValueError(
            f"knowledge_vector_read_primary must be 'neo4j' or 'postgres', got "
            f"{read_primary!r}"
        )
    if read_primary == "postgres" and not dsn:
        # Asked for the pgvector primary with no pgvector. Refusing is the point: serving
        # Neo4j quietly would make a MISCONFIGURED deployment indistinguishable from a
        # correctly pre-cutover one, and the operator would read "cutover complete".
        raise ValueError(
            "knowledge_vector_read_primary='postgres' requires KNOWLEDGE_VECTOR_DB_URL"
        )
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
        if read_primary == "postgres":
            # ⚠️ POST-CUTOVER this is not a degraded WRITE, it is the PRIMARY being down,
            # and the fallback is serving reads from the store the deployment has stopped
            # treating as authoritative. That is still the right call while Neo4j's indexes
            # exist — a stale answer beats no search — but it must not be quiet: an operator
            # reading normal-looking results has no other signal that the cutover is not in
            # effect right now.
            #
            # It stops being survivable at T25 ③. Once the Neo4j vector indexes are dropped,
            # this line serves an EMPTY search rather than a stale one, which is exactly why
            # dropping them is a separate act with its own evidence and not part of the flip.
            logger.error(
                "T25: CUTOVER NOT IN EFFECT — reads are falling back to Neo4j because the "
                "pgvector primary is unreachable. Results are being served by the store "
                "this deployment no longer treats as authoritative."
            )
        return primary

    # T25q/§3.3c — the `anchor_score` resolver, supplied ONLY when the graph can serve it.
    #
    # ⚠️ The condition is the safeguard. On a `neo4j` backend the AGE graph does not hold the
    # entities, so a resolver would answer NOTHING for every hit — and `glossary.py`'s
    # `anchor_score or 0.0` turns that into a column of zeroes and a silent fall back to raw
    # cosine order. Leaving the collaborator OUT keeps the key absent, so a consumer that ranks
    # by it raises instead. Absent is loud; present-and-empty is not.
    anchor_scores = None
    if configured_backend() == "age":
        try:
            from app.adapters.age_anchor_scores import age_anchor_scores
            from app.db.age_pool import age_pool

            anchor_scores = age_anchor_scores(age_pool())
        except Exception as exc:                       # noqa: BLE001 — pool not initialised
            # Fail toward the OLD behaviour (key absent, consumer raises), never toward a
            # resolver that cannot answer.
            logger.warning(
                "T25q: no anchor_score resolver (%s) — entity hits keep the key ABSENT, so a "
                "two-layer ranker raises rather than ranking by raw cosine.", exc,
            )
            anchor_scores = None

    pg = PgVectorStore(pool, entity_exists=entity_exists, anchor_scores=anchor_scores)
    # T25 — the cutover. `DualWriteVectorStore` is symmetric in construction: it writes both
    # and reads the FIRST. So cutting over is swapping the pair, not a second class. Post-
    # cutover the shadow runs in reverse (Neo4j compared against pgvector), which keeps the
    # old store answering alongside the new one and keeps `vector_shadow_read_overlap`
    # meaningful in the direction that matters now.
    cutover = read_primary == "postgres"
    first, second = (pg, primary) if cutover else (primary, pg)
    # ⚠️ PASSAGES ONLY, and this is the whole reason the switch is not a single primary.
    # `PgVectorStore` OMITS `anchor_score` from an entity hit by design
    # (D-T25B-PG-ANCHOR-SCORE) — the score is bucket-relative and recomputed on its own
    # schedule, so a copy on the vector row would be confidently stale. Entity reads RANK by
    # it. Cutting entities over would silently reorder every two-layer retrieval.
    #
    # Caught by `test_the_provider_keeps_neo4j_as_primary`, a tripwire written at T25b for
    # exactly this day. It fired on the argument swap before this shipped.
    # T25s — the ENTITY scope moves only when the two-layer ranking factor can be served.
    #
    # §3.3 held entities on Neo4j because `PgVectorStore` omits `anchor_score`. §3.3c answered
    # that (join from the authority, not a copy) and T25r wired the resolver — so the condition
    # is now exactly "is there a resolver", and it is SELF-GUARDING: on a `neo4j` backend the
    # provider supplies none, so entity reads stay where they can be ranked. No second switch
    # to keep in step with the first.
    #
    # ⚠️ The alternative — flipping entities on a bare `cutover` — is the §9.1 failure in a new
    # place: reads served by a store that cannot rank them, which is not an error, just a
    # quietly worse ordering.
    scopes = read_scopes(cutover=cutover, has_anchor_resolver=anchor_scores is not None)
    entity_ready = "entity" in scopes and cutover
    if cutover:
        logger.info(
            "T25: vector PASSAGE reads served by POSTGRES; Neo4j is the shadow. "
            "ENTITY reads %s.",
            "ALSO on Postgres (anchor_score joined from the graph, §3.3c)" if entity_ready
            else "stay on Neo4j (no anchor_score resolver — see T25r)",
        )
    return DualWriteVectorStore(
        first,
        second,
        shadow_read_rate=settings.knowledge_vector_shadow_read_rate,
        primary_read_scopes=scopes,
    )
