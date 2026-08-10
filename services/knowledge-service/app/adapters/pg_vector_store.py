"""Postgres implementation of the `VectorStore` port (plan T23).

Runs against the image T22 builds — PG18 + pgvector + pgvectorscale
(`loreweave/postgres-knowledge:18`). The point of this backend is one property Neo4j
cannot give us: **the tenant filter goes to the planner.** Neo4j's vector index cannot
filter by tenant, so `Neo4jVectorStore` over-fetches by 10x and discards out-of-scope rows
afterwards; the `oversample_factor` that compensates was deliberately kept OFF the port
(T14) because it is one backend's weakness, not a domain knob. Here the predicate sits in
the same `WHERE` as the `ORDER BY embedding <=> $q`, and StreamingDiskANN streams it during
the index scan rather than after it. `tests/integration/db/test_pg_vector_store.py` asserts
that with `EXPLAIN`, because "the filter is in the planner" is a claim about a query plan
and reading the SQL cannot prove it.

── WHY PER-DIM TABLES, AND WHY THAT IS NOT A CHOICE ─────────────────────────────────────
`vector(n)` is a TYPED column: one table cannot hold 384- and 3072-dim embeddings. So the
per-dim split is structural, and the dim set has to be closed for the table name to be
safe to interpolate. It already is — `SUPPORTED_PASSAGE_DIMS`, which `passages.py` has been
validating against for the same reason (Cypher could not parameterise a property name;
SQL cannot parameterise a relation name). Same barrier, same closed set, one place.

── THE ENTITY-EXISTENCE ORACLE, AND WHY IT IS A CONSTRUCTOR ARGUMENT ────────────────────
The port says `upsert` returns False when the target entity did not exist — a delete that
landed between embedding and write. Neo4j can answer that because the entity node and its
embedding are THE SAME OBJECT: `MATCH … SET` matches nothing and reports it.

In a vector-only Postgres they are not the same object. The embedding row is the only
object, and an `INSERT` always succeeds — so this adapter cannot observe the race at all.
Returning `True` unconditionally would satisfy the signature while silently dropping a
guarantee the caller relies on, which is the failure mode this refactor keeps finding. So
the oracle is an explicit dependency: the composition root passes `entity_exists` (the KG
store does know), and without it entity upserts raise `NotImplementedError` rather than
guess. Passage writes need no oracle and work either way. This mirrors how `TruthStore`
(T19) refuses a capability it does not have instead of faking one.

── DIVERGENCE FROM THE PORT'S INDEX-LIFECYCLE CONTRACT (a finding, not a workaround) ─────
`ensure_index` is documented as returning `{level: index_name}` for chapter/part/book. That
shape is Neo4j's per-project SUMMARY index model, and it does not describe this backend:

  1. **Summary vectors are a third family the port never modelled.** `search`/`upsert` take
     `VectorScope = passage | entity`, while `ensure_index`/`drop_index`/`list_indexes`
     address `summary_embedding` on Chapter/Part/Book nodes — served by
     `query_summary_index`, which is not on the port at all. The two halves of the port
     describe different vectors.
  2. **There is no per-project index here, on purpose.** Minting one per project would
     rebuild the ~30 000-index scheme the port's own docstring cites as the reason to move.

So this returns a `{scope: index_name}` map over the shared per-dim indexes it really owns,
and the names it mints carry **no project id** — `parse_summary_index_name` returns None for
every one of them. That is the load-bearing safety property, not a formatting detail: the
prune-orphans admin path decides what to drop by parsing a project out of an index name, so
an unparseable name is what stops it offering to drop an index that serves every tenant.
On this backend orphans are ROWS, not indexes, and reclaiming them is a delete with
different safety properties that must not hide behind a method called `drop_index`.

Reconciling the port's two halves is T24/T25 work; it is written down here rather than
smoothed over, because a `{level: …}` map with plausible names would have looked correct.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Awaitable, Callable

import asyncpg

from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS
from app.ports.vector_store import (
    EntityVectorRecord,
    PassageVectorRecord,
    VectorFilter,
    VectorHit,
    VectorRecord,
    VectorScope,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PgVectorStore",
    "entity_table",
    "ensure_vector_schema",
    "index_name",
    "parse_vector_index_name",
    "passage_table",
]


# ── names ────────────────────────────────────────────────────────────────────
#
# Every relation and index name in this module is BUILT here from a dim that has been
# checked against the closed set. Nothing accepts a name from a caller except
# `drop_index`, which re-parses it with the grammar below before it reaches SQL.


def passage_table(dim: int) -> str:
    _check_dim(dim)
    return f"passage_vectors_{dim}"


def entity_table(dim: int) -> str:
    _check_dim(dim)
    return f"entity_vectors_{dim}"


def index_name(scope: VectorScope, dim: int, kind: str) -> str:
    if scope not in ("passage", "entity"):
        raise ValueError(f"unknown vector scope {scope!r}")
    if kind not in ("emb", "tenant"):
        raise ValueError(f"unknown index kind {kind!r}")
    _check_dim(dim)
    return f"{scope}_vectors_{dim}_{kind}"


_INDEX_NAME_RE = re.compile(r"^(?P<scope>passage|entity)_vectors_(?P<dim>\d+)_(?P<kind>emb|tenant)$")


def parse_vector_index_name(name: str) -> dict[str, str] | None:
    """Inverse of `index_name`, or None. Deliberately yields NO project id: see the module
    docstring — an index here serves every tenant, and a name that looked project-scoped
    would invite the prune-orphans path to drop it."""
    m = _INDEX_NAME_RE.match(name)
    if m is None:
        return None
    if int(m.group("dim")) not in SUPPORTED_PASSAGE_DIMS:
        return None
    return {"name": name, "scope": m.group("scope"), "dim": m.group("dim"), "kind": m.group("kind")}


def _check_dim(dim: int) -> None:
    if dim not in SUPPORTED_PASSAGE_DIMS:
        raise ValueError(
            f"unsupported embedding dim {dim!r}; must be one of {SUPPORTED_PASSAGE_DIMS}. "
            "This is the injection barrier for the interpolated relation name, not a "
            "capacity limit — widen the closed set deliberately, never the check."
        )


def _vector_literal(embedding: list[float]) -> str:
    """pgvector's text input form. Passed as text and cast with `::vector` at the call
    site rather than pulling in the `pgvector` package for a codec — one dependency, for
    one format, that this module would be the only user of."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


# ── schema ───────────────────────────────────────────────────────────────────

_PASSAGE_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         text NOT NULL,
    project_id      text,
    source_type     text NOT NULL,
    source_id       text NOT NULL,
    chunk_index     integer NOT NULL,
    text            text NOT NULL,
    embedding       vector({dim}) NOT NULL,
    embedding_model text,
    is_hub          boolean NOT NULL DEFAULT false,
    chapter_index   integer,
    canon           boolean NOT NULL DEFAULT true,
    block_index     integer,
    source_lang     text NOT NULL DEFAULT 'unknown',
    mixed           boolean NOT NULL DEFAULT false,
    content_hash    text,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    -- Identity is (user, source, chunk): re-embedding an edited chunk must REPLACE. A
    -- surrogate key alone would let a re-embed double every hit's recall silently.
    UNIQUE (user_id, source_type, source_id, chunk_index)
)
"""

_ENTITY_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    entity_id         text PRIMARY KEY,
    user_id           text NOT NULL,
    embedding         vector({dim}) NOT NULL,
    embedding_model   text NOT NULL,
    embedding_version integer NOT NULL,
    updated_at        timestamptz NOT NULL DEFAULT now()
)
"""


async def ensure_vector_schema(pool: asyncpg.Pool, dims: tuple[int, ...] | None = None) -> None:
    """Idempotent create of the tables and indexes for each dim. Safe on every start.

    Both extensions are created here rather than assumed: the T22 image ships them, but a
    self-hoster pointing at their own Postgres gets a comprehensible error at boot instead
    of a confusing one on the first `<=>`.
    """
    for dim in dims or SUPPORTED_PASSAGE_DIMS:
        _check_dim(dim)
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE")
        for dim in dims or SUPPORTED_PASSAGE_DIMS:
            ptable, etable = passage_table(dim), entity_table(dim)
            await conn.execute(_PASSAGE_DDL.format(table=ptable, dim=dim))
            await conn.execute(_ENTITY_DDL.format(table=etable, dim=dim))
            for scope, table in (("passage", ptable), ("entity", etable)):
                await conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {index_name(scope, dim, 'emb')} "
                    f"ON {table} USING diskann (embedding vector_cosine_ops)"
                )
            # The tenant b-tree is not redundant with the diskann index: it gives the
            # planner a filter-FIRST path for a small tenant, where scanning that tenant's
            # few hundred rows beats an approximate search it then has to filter. Which one
            # wins is the planner's call per query — that choice is the whole reason this
            # backend exists, and offering it only one option would decide it in advance.
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name('passage', dim, 'tenant')} "
                f"ON {ptable} (user_id, project_id)"
            )
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name('entity', dim, 'tenant')} "
                f"ON {etable} (user_id)"
            )


# ── the adapter ──────────────────────────────────────────────────────────────

# Columns returned for a passage hit, in the order the row is unpacked below.
_PASSAGE_ATTRS = (
    "text", "source_type", "source_id", "chunk_index",
    "is_hub", "chapter_index", "canon", "source_lang",
)

EntityExists = Callable[[str, str], Awaitable[bool]]


class PgVectorStore:
    """Holds a pool, the way `Neo4jVectorStore` holds a session and the fake holds a dict —
    a caller of the port must not be able to tell which.

    `query_rescore` is StreamingDiskANN's recall knob (`diskann.query_rescore`): how many
    approximate candidates get their exact distance recomputed before the top-k is chosen.
    It is a CONSTRUCTOR argument, not a port parameter, for the same reason
    `oversample_factor` never reached the port — it is one index implementation's
    recall/latency trade, and a caller that had to set it would be programming the backend.
    T24 measures it; leaving it None keeps the server default.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        entity_exists: EntityExists | None = None,
        query_rescore: int | None = None,
    ) -> None:
        self._pool = pool
        self._entity_exists = entity_exists
        if query_rescore is not None and query_rescore <= 0:
            raise ValueError(f"query_rescore must be positive, got {query_rescore!r}")
        self._query_rescore = query_rescore

    def build_search_sql(
        self,
        *,
        scope: VectorScope,
        user_id: str,
        embedding: list[float],
        dim: int,
        k: int = 10,
        filter: VectorFilter | None = None,
    ) -> tuple[str, list[object], list[str]]:
        """The query `search` runs, without running it. Returns `(sql, params, filters)`.

        Public so the integration test can `EXPLAIN` **this** statement rather than a copy
        of it: the T23 claim is that the tenant predicate reaches the planner, and a test
        that EXPLAINed its own re-typed SQL would keep passing after a change to the real
        one. Not part of the port — no caller outside this backend has any use for it.
        """
        f = filter or VectorFilter()
        if len(embedding) != dim:
            # The port passes `dim` separately ON PURPOSE — a mismatch is a caller bug.
            # Postgres would raise its own error here, but with the column's dim rather
            # than the caller's, which sends the reader to the wrong file.
            raise ValueError(f"embedding has {len(embedding)} values but dim={dim}")
        if scope not in ("passage", "entity"):
            raise ValueError(f"unknown vector scope {scope!r}")
        if scope == "entity":
            # Both of the port's entity-scope narrowings describe state that lives on the
            # ENTITY, and this store holds only vectors:
            #
            #   * `include_archived=False` — the DEFAULT — means "exclude archived
            #     entities". Neo4j runs a different query for it
            #     (`_FIND_BY_VECTOR_CYPHER_ACTIVE`); there is no `archived_at` here to run
            #     it against.
            #   * `project_id` narrows to one project. `EntityVectorRecord` carries no
            #     project at all, so the write path cannot store what the read path filters
            #     on — a port gap (T14), not something this adapter can close.
            #
            # Silently ignoring either would return archived and cross-project entities
            # from a call that asked for neither, and the CUTOVER is where that would
            # first happen — a backend swap quietly widening a result set is precisely
            # what QC-3 exists to catch. So it refuses, and the entity read path is owed
            # by T24, where the dual-write writer that could maintain those columns is
            # built. Entity UPSERT works today, so T24 has rows to measure.
            raise NotImplementedError(
                "PgVectorStore cannot serve entity-scope search yet: `include_archived` "
                "and `project_id` describe entity lifecycle state that this store does "
                "not hold, and answering without them would silently widen every result "
                "set on cutover. Owed by T24 (dual-write). Use the Neo4j store for entity "
                "search until then; passage search is unaffected."
            )
        table = passage_table(dim)

        # Clauses are appended only when the filter is actually set. The alternative —
        # `($2::text IS NULL OR project_id = $2)` for every field — keeps the SQL constant
        # but hands the planner a predicate it cannot use for an index path, which would
        # give away the property this backend exists for.
        where = ["user_id = $1"]
        params: list[object] = [user_id]
        applied: list[str] = []

        def _add(sql_col: str, value: object, label: str) -> None:
            params.append(value)
            where.append(f"{sql_col} = ${len(params)}")
            applied.append(label)

        if f.project_id is not None:
            _add("project_id", f.project_id, "project")
        if f.embedding_model is not None:
            _add("embedding_model", f.embedding_model, "model")
        if f.source_type is not None:
            _add("source_type", f.source_type, "source_type")
        if not f.include_drafts:
            where.append("canon")
            applied.append("canon")

        params.append(_vector_literal(embedding))
        vec = f"${len(params)}::vector"
        params.append(k)
        limit = f"${len(params)}"

        select = (
            f"SELECT id::text AS record_id, 1 - (embedding <=> {vec}) AS score, "
            f"{', '.join(_PASSAGE_ATTRS)}"
        )
        sql = (
            f"{select} FROM {table} WHERE {' AND '.join(where)} "
            f"ORDER BY embedding <=> {vec} LIMIT {limit}"
        )
        return sql, params, applied

    async def search(
        self,
        *,
        scope: VectorScope,
        user_id: str,
        embedding: list[float],
        dim: int,
        k: int = 10,
        filter: VectorFilter | None = None,
    ) -> list[VectorHit]:
        started = time.perf_counter()
        sql, params, applied = self.build_search_sql(
            scope=scope, user_id=user_id, embedding=embedding, dim=dim, k=k, filter=filter,
        )
        table = passage_table(dim)  # entity scope raised in the builder above

        async with self._pool.acquire() as conn:
            if self._query_rescore is None:
                rows = await conn.fetch(sql, *params)
            else:
                # SET LOCAL inside an explicit transaction, NOT bare on a pooled
                # connection. Bare, `SET LOCAL` warns "can only be used in transaction
                # blocks" and does nothing — a recall knob that silently never applies —
                # while plain `SET` would leak this query's setting to whichever request
                # borrows the connection next.
                async with conn.transaction():
                    await conn.execute(
                        f"SET LOCAL diskann.query_rescore = {int(self._query_rescore)}"
                    )
                    rows = await conn.fetch(sql, *params)

        out = [
            VectorHit(
                record_id=r["record_id"],
                score=float(r["score"]),
                scope=scope,
                attributes={a: r[a] for a in _PASSAGE_ATTRS},
            )
            for r in rows
        ]

        logger.debug(
            "vector search: backend=postgres partition=%s scope=%s dim=%d k=%d "
            "filters=%s hits=%d rescore=%s elapsed_ms=%d",
            table, scope, dim, k, ",".join(applied) or "none", len(out),
            self._query_rescore if self._query_rescore is not None else "server-default",
            int((time.perf_counter() - started) * 1000),
        )
        return out

    async def upsert(self, record: VectorRecord) -> bool:
        started = time.perf_counter()
        dim = record.embedding_dim
        if len(record.embedding) != dim:
            raise ValueError(f"embedding has {len(record.embedding)} values but dim={dim}")

        if isinstance(record, PassageVectorRecord):
            table = passage_table(dim)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO {table} (
                        user_id, project_id, source_type, source_id, chunk_index, text,
                        embedding, embedding_model, is_hub, chapter_index, canon,
                        block_index, source_lang, mixed, content_hash
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7::vector,$8,$9,$10,$11,$12,$13,$14,$15)
                    ON CONFLICT (user_id, source_type, source_id, chunk_index) DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        text = EXCLUDED.text,
                        embedding = EXCLUDED.embedding,
                        embedding_model = EXCLUDED.embedding_model,
                        is_hub = EXCLUDED.is_hub,
                        chapter_index = EXCLUDED.chapter_index,
                        canon = EXCLUDED.canon,
                        block_index = EXCLUDED.block_index,
                        source_lang = EXCLUDED.source_lang,
                        mixed = EXCLUDED.mixed,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = now()
                    """,
                    record.user_id, record.project_id, record.source_type, record.source_id,
                    record.chunk_index, record.text, _vector_literal(record.embedding),
                    record.embedding_model, record.is_hub, record.chapter_index, record.canon,
                    record.block_index, record.source_lang, record.mixed, record.content_hash,
                )
            written = True

        elif isinstance(record, EntityVectorRecord):
            if self._entity_exists is None:
                # See the module docstring. The alternative is returning True and quietly
                # dropping the port's missing-target guarantee, which no caller would see.
                raise NotImplementedError(
                    "PgVectorStore cannot tell whether an entity still exists — its vectors "
                    "live in a different database from the entity. Pass `entity_exists` at "
                    "construction (the KG store knows) so the port's False-on-missing-target "
                    "return keeps meaning what it says."
                )
            if not await self._entity_exists(record.user_id, record.entity_id):
                logger.debug(
                    "vector upsert: backend=postgres entity absent id=%s", record.entity_id
                )
                return False
            table = entity_table(dim)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO {table} (
                        entity_id, user_id, embedding, embedding_model, embedding_version
                    ) VALUES ($1,$2,$3::vector,$4,$5)
                    ON CONFLICT (entity_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        embedding = EXCLUDED.embedding,
                        embedding_model = EXCLUDED.embedding_model,
                        embedding_version = EXCLUDED.embedding_version,
                        updated_at = now()
                    """,
                    record.entity_id, record.user_id, _vector_literal(record.embedding),
                    record.embedding_model, record.embedding_version,
                )
            written = True
        else:
            raise TypeError(f"unknown vector record type {type(record).__name__}")

        logger.debug(
            "vector upsert: backend=postgres scope=%s dim=%d written=%s elapsed_ms=%d",
            record.scope, dim, written, int((time.perf_counter() - started) * 1000),
        )
        return written

    async def ensure_index(
        self, *, project_id: str, embedding_model_uuid: str, embedding_dimension: int,
    ) -> dict[str, str]:
        """Ensure the per-dim tables and their indexes. `project_id` and
        `embedding_model_uuid` are ACCEPTED AND UNUSED — see the module docstring: an index
        here is shared by every tenant on purpose, and minting one per project would
        rebuild the index explosion this backend exists to end. Returns a `{scope: name}`
        map, not the port's `{level: name}`, because the levels describe summary vectors
        this store does not hold.
        """
        _check_dim(embedding_dimension)
        await ensure_vector_schema(self._pool, dims=(embedding_dimension,))
        names = {
            scope: index_name(scope, embedding_dimension, "emb")
            for scope in ("passage", "entity")
        }
        logger.debug(
            "vector ensure_index: backend=postgres dim=%d indexes=%d project=%s (unused)",
            embedding_dimension, len(names), project_id,
        )
        return names

    async def drop_index(self, *, name: str) -> None:
        """Idempotent drop, restricted to names this store mints. SQL cannot parameterise a
        relation name, so re-parsing the name IS the injection barrier — the same role
        `parse_summary_index_name` plays for Cypher, and it must not be bypassable by
        arriving through the port instead of through here.
        """
        if parse_vector_index_name(name) is None:
            raise ValueError(f"refusing to DROP an index this store does not own: {name!r}")
        async with self._pool.acquire() as conn:
            await conn.execute(f"DROP INDEX IF EXISTS {name}")
        logger.debug("vector drop_index: backend=postgres name=%s", name)

    async def list_indexes(self) -> list[dict[str, str]]:
        """Only the indexes this store owns. The filter is `parse_vector_index_name`, not a
        `LIKE` — the admin prune endpoint acts on whatever this returns, so including an
        index the store does not own would let it offer to drop someone else's.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
            )
        out = []
        for r in rows:
            parsed = parse_vector_index_name(r["indexname"])
            if parsed is not None:
                out.append(parsed)
        return out
