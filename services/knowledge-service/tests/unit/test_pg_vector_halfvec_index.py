"""QC-3 sign-off (PO 2026-08-21) — halfvec HNSW replaces StreamingDiskANN.

On the real corpus diskann recalled 0.836 with a worst query at 0.500 and was the slowest
non-fp16 cell; halfvec_hnsw scored 1.000 at ~41 % of the table bytes. It also reaches dims
the alternative could not — pgvector caps HNSW at 2000 dims for `vector` but 4000 for
`halfvec`, so 2560 and 3072 get an exact-free path for the first time.

These tests exist because the adoption has TWO silent failure modes, neither of which raises
and neither of which any test covered before this file: the whole vector suite (74 tests)
stayed green while the index kind and both query expressions were rewritten.
"""

from __future__ import annotations

import pytest

from app.adapters.pg_vector_store import (
    PgVectorStore,
    emb_index_expr,
    index_name,
)

DIMS = (384, 1024, 1536, 2560, 3072)


def _sql(scope, dim):
    store = PgVectorStore.__new__(PgVectorStore)
    sql, _params, _applied = PgVectorStore.build_search_sql(
        store, scope=scope, user_id="u1", embedding=[0.1] * dim, dim=dim, k=5,
    )
    return sql


@pytest.mark.parametrize("dim", DIMS)
@pytest.mark.parametrize("scope", ["passage", "entity"])
def test_the_ORDER_BY_is_the_INDEX_expression_or_the_index_is_never_used(scope, dim):
    """The failure mode with no error message.

    pgvector uses an expression index only when the query's ORDER BY is textually that
    expression. An ORDER BY that drifts by one cast still returns *correct rows* — it just
    stops using the index and becomes a seq scan. Nothing raises; the symptom is latency on
    a table big enough for latency to matter, i.e. long after the change shipped.
    """
    sql = _sql(scope, dim)
    expr = emb_index_expr(dim)
    order = sql.split("ORDER BY", 1)[1]
    assert order.lstrip().startswith(expr), (
        f"ORDER BY does not open with the index expression {expr!r} — the halfvec HNSW "
        f"index cannot be used and this query is a sequential scan. Got: {order[:120]!r}"
    )


@pytest.mark.parametrize("dim", DIMS)
@pytest.mark.parametrize("scope", ["passage", "entity"])
def test_the_SCORE_agrees_with_the_ordering_it_is_returned_in(scope, dim):
    """`score` is computed from the same halfvec distance as the ORDER BY.

    Scoring in fp32 while ordering in fp16 makes rows that are correctly ordered but whose
    scores are not monotonic in that order — a caller sorting or thresholding by `score`
    then disagrees with the database about its own result set.
    """
    sql = _sql(scope, dim)
    expr = emb_index_expr(dim)
    score = sql.split(" AS score", 1)[0]
    assert expr in score, (
        f"score is not computed from {expr!r}, so it can disagree with the ordering: "
        f"{score[-140:]!r}"
    )


def test_the_retired_diskann_index_name_is_still_MINTABLE_so_it_can_be_dropped():
    """`ensure_vector_schema` names the old `emb` index in order to DROP it. If
    `index_name` stopped accepting that kind, schema-ensure would raise at boot on every
    deployment — which is exactly what happened while writing this change.
    """
    assert index_name("passage", 1024, "emb") == "passage_vectors_1024_emb"
    assert index_name("entity", 1024, "emb_hv") == "entity_vectors_1024_emb_hv"


def test_the_new_index_does_NOT_reuse_the_old_name():
    """Reusing `emb` with CREATE INDEX IF NOT EXISTS would find the existing diskann index
    on every deployment that already ran this function and silently keep it: the schema
    would say halfvec and the server would serve diskann, with nothing failing anywhere.
    """
    assert index_name("passage", 1024, "emb_hv") != index_name("passage", 1024, "emb")


@pytest.mark.parametrize("dim", DIMS)
def test_the_expression_names_the_ROW_dim_not_a_fixed_one(dim):
    assert emb_index_expr(dim) == f"(embedding::halfvec({dim}))"


# ── the index-LIFECYCLE surface, which LOW-4 flagged as the one that drifts ──────────────


def test_the_new_index_name_ROUND_TRIPS_or_drop_index_refuses_to_drop_it():
    """`drop_index` re-parses the name as its injection barrier and raises on anything this
    store does not own. When the regex still matched only `emb|tenant`, the admin path
    refused to drop the very index `ensure_vector_schema` had just created — the store could
    build an index it could not remove.
    """
    from app.adapters.pg_vector_store import parse_vector_index_name

    parsed = parse_vector_index_name(index_name("entity", 1024, "emb_hv"))
    assert parsed is not None, "the halfvec index name does not parse — drop_index will refuse it"
    assert parsed["kind"] == "emb_hv"


def test_the_RETIRED_name_still_parses_so_an_operator_can_drop_it_by_hand():
    """A deployment that has not yet restarted into the new schema-ensure still has the
    diskann index. Refusing to parse its name would leave it unremovable through the port.
    """
    from app.adapters.pg_vector_store import parse_vector_index_name

    parsed = parse_vector_index_name("entity_vectors_1024_emb")
    assert parsed is not None and parsed["kind"] == "emb"


def test_a_name_this_store_does_not_mint_is_still_REFUSED():
    """The control for the two above: widening the regex must not turn the barrier off."""
    from app.adapters.pg_vector_store import parse_vector_index_name

    assert parse_vector_index_name("entity_vectors_1024_bogus") is None
    assert parse_vector_index_name("users_vectors_1024_emb_hv") is None
    assert parse_vector_index_name("entity_vectors_999_emb_hv") is None


@pytest.mark.asyncio
async def test_ensure_index_advertises_the_index_that_EXISTS_not_the_dropped_one():
    """`ensure_vector_schema` drops the `emb` index. Returning that name would hand callers a
    relation that no longer exists, and `drop_index` would no-op on it (`IF EXISTS`) while
    the real index stayed — the admin surface silently managing nothing.
    """
    from unittest.mock import AsyncMock, patch

    store = PgVectorStore.__new__(PgVectorStore)
    store._pool = object()
    with patch("app.adapters.pg_vector_store.ensure_vector_schema", new_callable=AsyncMock):
        names = await PgVectorStore.ensure_index(
            store, project_id="p1", embedding_model_uuid="m1", embedding_dimension=1024,
        )
    assert names["entity"].endswith("_emb_hv"), names
    assert names["passage"].endswith("_emb_hv"), names


# ── MED-2 — the entity-vector identity has no tenant. TICKETED, not fixed. ────────────────
#
# QC-3 sign-off (PO 2026-08-21): MED-2 becomes a migration ticket rather than a review's fix,
# because `PRIMARY KEY (user_id, entity_id)` is a schema change on a live table and rule 7's
# ledger discipline makes it a step of its own.
#
#   MIGRATION STEP (owed): entity_vectors_{dim}
#     PRIMARY KEY (entity_id)  ->  PRIMARY KEY (user_id, entity_id)
#     ON CONFLICT (entity_id)  ->  ON CONFLICT (user_id, entity_id)
#   and DROP the `user_id = EXCLUDED.user_id` assignment, which only exists because the
#   conflict target cannot currently carry the tenant.
#
# The hazard, stated once: uniqueness rests entirely on `entity_canonical_id` folding
# `user_id` into the hash — the property T35 exists to RETIRE — and the sibling passage table
# already keys the tenant explicitly (UNIQUE (user_id, source_type, source_id, chunk_index)).
# If two tenants ever mint one id the write does not fail; `DO UPDATE SET user_id =
# EXCLUDED.user_id` transfers ownership silently, and because reads are tenant-filtered the
# first tenant's vector just disappears from their searches.
#
# The tests below are the ticket's tripwire. They assert the CURRENT, KNOWN-WRONG shape, so
# the migration cannot land without deliberately rewriting them — and so the hazard cannot be
# quietly forgotten in the meantime. They are expected to be edited, once, by that migration.


def test_MED2_the_entity_table_still_keys_on_entity_id_ALONE():
    from app.adapters.pg_vector_store import _ENTITY_DDL

    assert "entity_id         text PRIMARY KEY" in _ENTITY_DDL, (
        "the entity-vector primary key changed. If this is MED-2's migration landing, "
        "update this tripwire and the ON CONFLICT test below together — and delete the "
        "`user_id = EXCLUDED.user_id` assignment, which only exists to work around the "
        "tenant-less conflict target."
    )


def test_MED2_the_conflict_handler_still_REWRITES_the_owner():
    """Pinned so the silent-ownership-transfer is discoverable from the tests, not only from
    a review note. This assertion documents a defect; it is not endorsing it."""
    import inspect

    from app.adapters import pg_vector_store

    src = inspect.getsource(pg_vector_store)
    assert "ON CONFLICT (entity_id) DO UPDATE SET" in src
    assert "user_id = EXCLUDED.user_id" in src, (
        "the owner-rewriting conflict handler is gone — if MED-2's migration landed, this "
        "tripwire and the PRIMARY KEY one above should both be updated in that commit"
    )
