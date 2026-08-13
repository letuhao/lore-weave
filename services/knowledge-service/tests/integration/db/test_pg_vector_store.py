"""`PgVectorStore` against a live pgvector Postgres (plan T23).

Two different things are proved here, and conflating them would weaken both.

**The contract** — ranking, tenant scoping, dim routing, replace-on-re-embed, the
`False`-on-missing-entity return. `FakeVectorStore` already enforces these in unit tests;
this is the run that says the real backend agrees, the same role QC-2 plays for the graph
stores.

**The reason this backend exists** — that the tenant predicate reaches the PLANNER. Neo4j's
vector index cannot filter by tenant, so `Neo4jVectorStore` over-fetches 10x and discards
afterwards. That is the cost the whole of Phase 3 is paid to remove, and it is a claim about
a query plan: reading the SQL cannot prove it, and a test that asserted on the SQL string
would pass just as happily if the planner ignored the predicate. So the plan is EXPLAINed,
and the assertion is about WHICH NODE evaluates `user_id` — the one that reads the table,
never a node above a scan that already returned every tenant's rows.

The EXPLAINed statement comes from `build_search_sql`, the same builder `search` uses. A
test that re-typed the query would keep passing after the real one changed.

Requires TEST_VECTOR_DB_URL (see the `vector_pool` fixture); skipped without it.
"""

from __future__ import annotations

import json
import random

import pytest

from app.adapters.pg_vector_store import (
    PgVectorStore,
    ensure_vector_schema,
    entity_table,
    index_name,
    parse_vector_index_name,
    passage_table,
)
from app.ports.vector_store import EntityVectorRecord, PassageVectorRecord, VectorFilter

pytestmark = pytest.mark.asyncio

_DIM = 384
_OTHER_DIM = 1536
_USER = "vec-user-1"
_OTHER_USER = "vec-user-2"
_PROJECT = "vec-proj-1"


def _axis(i: int, dim: int = _DIM) -> list[float]:
    """A unit vector along axis `i`. Distinct axes are exactly orthogonal, so the expected
    ranking is arithmetic rather than a guess about a random draw."""
    v = [0.0] * dim
    v[i] = 1.0
    return v


def _blend(a: int, b: int, w: float, dim: int = _DIM) -> list[float]:
    v = [0.0] * dim
    v[a] = 1.0 - w
    v[b] = w
    return v


def _passage(source_id: str, embedding: list[float], **kw) -> PassageVectorRecord:
    return PassageVectorRecord(
        user_id=kw.pop("user_id", _USER),
        project_id=kw.pop("project_id", _PROJECT),
        source_type=kw.pop("source_type", "chapter"),
        source_id=source_id,
        chunk_index=kw.pop("chunk_index", 0),
        text=kw.pop("text", f"text for {source_id}"),
        embedding=embedding,
        embedding_dim=kw.pop("embedding_dim", len(embedding)),
        **kw,
    )


@pytest.fixture
async def store(vector_pool):
    await ensure_vector_schema(vector_pool, dims=(_DIM, _OTHER_DIM))
    return PgVectorStore(vector_pool)


def _source_ids(hits) -> list[str]:
    return [h.attributes["source_id"] for h in hits]


# ── the contract ─────────────────────────────────────────────────────────────


async def test_results_are_ordered_by_similarity_not_by_insertion(store):
    """Inserted worst-first, so a backend that returned insertion order would produce the
    exact reverse of the expected list rather than something merely different."""
    await store.upsert(_passage("far", _axis(1)))
    await store.upsert(_passage("mid", _blend(0, 1, 0.5)))
    await store.upsert(_passage("near", _axis(0)))

    hits = await store.search(scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM, k=3)
    assert _source_ids(hits) == ["near", "mid", "far"]
    assert hits[0].score > hits[1].score > hits[2].score
    # `<=>` is cosine DISTANCE; the port promises similarity. An adapter that forgot the
    # `1 -` would still rank correctly and be wrong about every score it reported.
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)
    assert hits[2].score == pytest.approx(0.0, abs=1e-6)


async def test_k_truncates_after_ranking_not_before(store):
    await store.upsert(_passage("far", _axis(1)))
    await store.upsert(_passage("near", _axis(0)))
    hits = await store.search(scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM, k=1)
    assert _source_ids(hits) == ["near"]


async def test_another_users_vectors_are_never_returned(store):
    """The bite for this one is the whole point of T23: delete `user_id = $1` from
    `build_search_sql` and this goes red, together with the planner test below."""
    await store.upsert(_passage("mine", _axis(0)))
    await store.upsert(_passage("theirs", _axis(0), user_id=_OTHER_USER))

    hits = await store.search(scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM, k=10)
    assert _source_ids(hits) == ["mine"]


async def test_a_query_does_not_match_a_different_dim_family(store):
    """`vector(n)` is a typed column, so the dim families are separate TABLES here. That
    makes cross-dim leakage structurally impossible — which is worth pinning, because it is
    the property that lets the table name be interpolated from a closed set."""
    await store.upsert(_passage("d384", _axis(0, _DIM), embedding_dim=_DIM))
    await store.upsert(_passage("d1536", _axis(0, _OTHER_DIM), embedding_dim=_OTHER_DIM))

    small = await store.search(scope="passage", user_id=_USER, embedding=_axis(0, _DIM),
                               dim=_DIM, k=10)
    big = await store.search(scope="passage", user_id=_USER, embedding=_axis(0, _OTHER_DIM),
                             dim=_OTHER_DIM, k=10)
    assert _source_ids(small) == ["d384"]
    assert _source_ids(big) == ["d1536"]


async def test_a_dim_that_disagrees_with_the_embedding_is_a_caller_bug(store):
    with pytest.raises(ValueError, match="dim=384"):
        await store.search(scope="passage", user_id=_USER, embedding=[1.0, 0.0], dim=_DIM, k=1)


async def test_project_filter_and_its_absence_mean_different_things(store):
    await store.upsert(_passage("p1", _axis(0), project_id="vec-proj-1"))
    await store.upsert(_passage("p2", _axis(0), project_id="vec-proj-2"))

    scoped = await store.search(scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM,
                                k=10, filter=VectorFilter(project_id="vec-proj-1"))
    unscoped = await store.search(scope="passage", user_id=_USER, embedding=_axis(0),
                                  dim=_DIM, k=10)
    assert _source_ids(scoped) == ["p1"]
    assert sorted(_source_ids(unscoped)) == ["p1", "p2"]


async def test_drafts_are_excluded_unless_asked_for(store):
    await store.upsert(_passage("published", _axis(0), canon=True))
    await store.upsert(_passage("draft", _axis(0), canon=False))

    default = await store.search(scope="passage", user_id=_USER, embedding=_axis(0),
                                 dim=_DIM, k=10)
    assert _source_ids(default) == ["published"]

    with_drafts = await store.search(scope="passage", user_id=_USER, embedding=_axis(0),
                                     dim=_DIM, k=10, filter=VectorFilter(include_drafts=True))
    assert sorted(_source_ids(with_drafts)) == ["draft", "published"]


async def test_re_embedding_the_same_chunk_replaces_it_and_keeps_its_id(store, vector_pool):
    """Identity is (user, source, chunk). An adapter that INSERTed a second row would double
    this passage's presence in every future result set and nothing would report it.

    The id must also SURVIVE the replace: it is what a caller stores to point back at a
    passage, so a re-embed that minted a new one would break every reference silently.
    """
    await store.upsert(_passage("ch1", _axis(0), text="before"))
    first = await store.search(scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM, k=10)

    await store.upsert(_passage("ch1", _axis(1), text="after"))
    async with vector_pool.acquire() as conn:
        count = await conn.fetchval(f"SELECT count(*) FROM {passage_table(_DIM)}")
    assert count == 1

    second = await store.search(scope="passage", user_id=_USER, embedding=_axis(1), dim=_DIM, k=10)
    assert second[0].attributes["text"] == "after"
    assert second[0].record_id == first[0].record_id


async def test_entity_vectors_round_trip_through_the_existence_oracle(store, vector_pool):
    """The oracle is a constructor dependency because a vector-only Postgres cannot see the
    entity — see the adapter docstring. Here both of its answers are exercised: a live
    entity is written, a deleted one is reported rather than raised."""
    live = {"e-live"}

    async def exists(user_id: str, entity_id: str) -> bool:
        return entity_id in live

    s = PgVectorStore(vector_pool, entity_exists=exists)
    rec = EntityVectorRecord(user_id=_USER, entity_id="e-live", embedding=_axis(0),
                             embedding_dim=_DIM, embedding_model="m", embedding_version=1)
    assert await s.upsert(rec) is True

    gone = EntityVectorRecord(user_id=_USER, entity_id="e-gone", embedding=_axis(0),
                              embedding_dim=_DIM, embedding_model="m", embedding_version=1)
    assert await s.upsert(gone) is False
    async with vector_pool.acquire() as conn:
        assert await conn.fetchval(f"SELECT count(*) FROM {entity_table(_DIM)}") == 1


# ── entity scope (T25b) ─────────────────────────────────────────────────────
#
# Entity upserts need the existence oracle (a vector-only Postgres cannot see the entity —
# see the adapter docstring), so these build their own store rather than using the shared
# `store` fixture. `store` is still requested so the schema exists before they write.


def _entity_store(vector_pool, live: set[str] | None = None):
    """A store whose oracle says yes to everything by default — these tests are about the
    SEARCH filters, and a missing-entity oracle would fail them for an unrelated reason."""

    async def exists(user_id: str, entity_id: str) -> bool:
        return True if live is None else entity_id in live

    return PgVectorStore(vector_pool, entity_exists=exists)


async def test_entity_search_excludes_archived_by_default(store, vector_pool):
    """This adapter REFUSED entity search until T25b, and the refusal was right: the port's
    two narrowings — `include_archived=False` (the DEFAULT) and `project_id` — describe
    lifecycle state a vector-only store did not hold, and answering anyway would have
    returned archived and cross-project entities to a call that asked for neither. The fix
    was never to ignore them; it was for the WRITE path to record them, which it now does.

    Archived exclusion is the default, so a caller that says nothing gets live entities only.
    """
    live = EntityVectorRecord(
        user_id=_USER, entity_id="e-live", embedding=_axis(0), embedding_dim=_DIM,
        embedding_model="m", embedding_version=1, project_id="p-1", archived=False,
    )
    retired = EntityVectorRecord(
        user_id=_USER, entity_id="e-retired", embedding=_axis(0), embedding_dim=_DIM,
        embedding_model="m", embedding_version=1, project_id="p-1", archived=True,
    )
    s = _entity_store(vector_pool)
    assert await s.upsert(live) is True
    assert await s.upsert(retired) is True

    hits = await s.search(scope="entity", user_id=_USER, embedding=_axis(0), dim=_DIM, k=10)
    ids = {h.record_id for h in hits}
    assert "e-live" in ids
    assert "e-retired" not in ids, (
        "an archived entity reached a default search — the retirement is invisible to "
        "retrieval, which is the split brain T28 spent a task removing"
    )

    # And the caller can still ask for them explicitly.
    all_hits = await s.search(
        scope="entity", user_id=_USER, embedding=_axis(0), dim=_DIM, k=10,
        filter=VectorFilter(include_archived=True),
    )
    assert {h.record_id for h in all_hits} >= {"e-live", "e-retired"}


async def test_entity_search_scopes_to_the_project(store, vector_pool):
    """The glossary FK is unique per (user, project), so an unscoped entity search returns an
    arbitrary project's node — the same defect that put every T27 lifecycle archive in the
    DLQ, reached from the read side."""
    s = _entity_store(vector_pool)
    for eid, proj in (("e-p1", "p-1"), ("e-p2", "p-2")):
        assert await s.upsert(EntityVectorRecord(
            user_id=_USER, entity_id=eid, embedding=_axis(0), embedding_dim=_DIM,
            embedding_model="m", embedding_version=1, project_id=proj,
        )) is True

    hits = await s.search(
        scope="entity", user_id=_USER, embedding=_axis(0), dim=_DIM, k=10,
        filter=VectorFilter(project_id="p-1"),
    )
    ids = {h.record_id for h in hits}
    assert "e-p1" in ids
    assert "e-p2" not in ids, "the project filter did not reach the query"


async def test_entity_search_does_not_cross_tenants(store, vector_pool):
    """The founding argument for this backend is that the tenant predicate reaches the
    PLANNER rather than being applied after an oversample. Entity scope must honour it too."""
    s = _entity_store(vector_pool)
    assert await s.upsert(EntityVectorRecord(
        user_id=_USER, entity_id="e-mine", embedding=_axis(0), embedding_dim=_DIM,
        embedding_model="m", embedding_version=1, project_id="p-1",
    )) is True
    hits = await s.search(
        scope="entity", user_id="someone-else", embedding=_axis(0), dim=_DIM, k=10,
    )
    assert [h.record_id for h in hits] == []


async def test_entity_hits_omit_anchor_score_rather_than_faking_it(store, vector_pool):
    """D-T25B-PG-ANCHOR-SCORE, pinned so it cannot be discovered the expensive way.

    The port promises entity hits carry `anchor_score` for two-layer ranking. This store
    holds vectors, and `anchor_score` is recomputed on its own schedule by the anchor pass —
    a copy on the vector row would be confidently STALE, which is worse than absent. So it is
    left OUT of the dict rather than set to None: a consumer that ranks by it raises a
    KeyError instead of silently multiplying every score by nothing.
    """
    s = _entity_store(vector_pool)
    assert await s.upsert(EntityVectorRecord(
        user_id=_USER, entity_id="e-1", embedding=_axis(0), embedding_dim=_DIM,
        embedding_model="m", embedding_version=1, project_id="p-1",
    )) is True
    hits = await s.search(scope="entity", user_id=_USER, embedding=_axis(0), dim=_DIM, k=10)
    assert hits
    assert "anchor_score" not in hits[0].attributes
    assert hits[0].attributes["project_id"] == "p-1"
    assert hits[0].attributes["archived"] is False


async def test_entity_lifecycle_columns_are_added_to_a_pre_t25b_table(store, vector_pool):
    """`CREATE TABLE IF NOT EXISTS` does NOTHING to an existing table.

    Without the explicit ALTER, the two columns would appear on every fresh test database —
    where this file runs — and on no deployment that already had data. The search would pass
    here and fail in production, on exactly the installations that matter. This simulates the
    old schema and asserts `ensure_vector_schema` repairs it.
    """
    table = entity_table(_DIM)
    async with vector_pool.acquire() as conn:
        await conn.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS project_id")
        await conn.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS archived")
        cols = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table)}
        assert "project_id" not in cols and "archived" not in cols

    await ensure_vector_schema(vector_pool, dims=(_DIM,))

    async with vector_pool.acquire() as conn:
        cols = {r["column_name"] for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table)}
    assert {"project_id", "archived"} <= cols, (
        "ensure_vector_schema did not repair a pre-T25b entity table"
    )


# ── search effort: a correctness setting, not a tuning one (T24) ─────────────


async def test_the_search_effort_setting_reaches_the_query(store, vector_pool):
    """T24 measured StreamingDiskANN's SERVER defaults at **recall@10 = 0.715** on the real
    passage corpus — three of ten neighbours missing, reported as success. At this store's
    defaults the same corpus returns 1.000, so the setting is load-bearing, and the way it
    fails is silent: `SET LOCAL` outside a transaction warns and does nothing.

    **The first version of this test asserted that on its own connection and the bite did
    not fire** — removing the transaction from `search()` left it green, because it was
    testing Postgres rather than the adapter. This one goes through `search()` and observes
    the setting's EFFECT: two stores configured differently must return different results.
    If the effort never reaches the query, both silently get the server default, their
    answers become identical, and this goes red.
    """
    await _seed_two_tenants(vector_pool, 3000)
    # The probe is a REAL ROW's vector, not a synthetic axis. A query that is out of the
    # corpus's distribution is near-equidistant from everything in 384 dimensions, so its
    # "top-10" is ten near-ties and recall measures float noise — the exact trap that made
    # this benchmark's first numbers unreadable. Querying with a row that exists gives a
    # nearest neighbour with a real margin: itself.
    async with vector_pool.acquire() as conn:
        probe = [float(x) for x in (await conn.fetchval(
            f"SELECT embedding::text FROM {passage_table(_DIM)} WHERE user_id = $1 LIMIT 1",
            _USER,
        )).strip("[]").split(",")]

    starved = PgVectorStore(vector_pool, query_search_list_size=1, query_rescore=1)
    generous = PgVectorStore(vector_pool, query_search_list_size=500, query_rescore=400)

    starved_hits = await starved.search(scope="passage", user_id=_USER, embedding=probe,
                                        dim=_DIM, k=10)
    generous_hits = await generous.search(scope="passage", user_id=_USER, embedding=probe,
                                          dim=_DIM, k=10)

    assert _source_ids(starved_hits) != _source_ids(generous_hits), (
        "a deliberately starved search returned exactly what a generous one did — the "
        "effort setting is not reaching the query, so every search is silently running at "
        "the server default that measured 0.715 recall on real data"
    )
    # NO recall-ordering assertion here, deliberately. This corpus is uniform random in 384
    # dimensions, where every point is near-orthogonal to every other and a top-10 is ten
    # near-ties separated by float noise — measured, not assumed: on that corpus the
    # benchmark scores EVERY backend between 0.2 and 0.4 and the ordering between them
    # flips run to run. Asserting "more effort ranks better" here would be a flaky test
    # dressed as a strong one.
    #
    # The VALUE of the setting is established where it can be: against the real passage
    # corpus, 0.715 → 1.000, in docs/measurements/2026-08-10-vector-backend-recall.md.
    # What this test owns is narrower and checkable — that the setting arrives at all.


async def test_search_effort_can_be_declined_but_not_half_declined(vector_pool):
    """A caller that configures the GUCs on its own pool must be able to opt out rather than
    pay a transaction per search — but opting out AND passing a value is a contradiction
    that would silently drop the value and run at the 0.715-recall server default."""
    assert PgVectorStore(vector_pool, search_effort=False).setter_sql() == ""
    with pytest.raises(ValueError, match="discards"):
        PgVectorStore(vector_pool, search_effort=False, query_rescore=400)


# ── the index lifecycle, and the prune-orphans path ──────────────────────────


async def test_list_indexes_reports_only_what_this_store_owns(store, vector_pool):
    async with vector_pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS not_ours (id int)")
        await conn.execute("CREATE INDEX IF NOT EXISTS not_ours_idx ON not_ours (id)")
    try:
        listed = await store.list_indexes()
        names = {i["name"] for i in listed}
        assert index_name("passage", _DIM, "emb") in names
        assert index_name("passage", _DIM, "tenant") in names
        # The admin prune endpoint acts on whatever this returns. One foreign index in the
        # list is one index it would offer to drop.
        assert "not_ours_idx" not in names
        assert all(parse_vector_index_name(n) is not None for n in names)
    finally:
        async with vector_pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS not_ours CASCADE")


async def test_drop_index_removes_one_of_ours_and_is_idempotent(store):
    name = index_name("passage", _DIM, "tenant")
    assert name in {i["name"] for i in await store.list_indexes()}
    await store.drop_index(name=name)
    assert name not in {i["name"] for i in await store.list_indexes()}
    await store.drop_index(name=name)  # DROP … IF EXISTS: a concurrent prune is not an error


async def test_ensure_index_is_idempotent_and_mints_no_per_project_index(store):
    """The port's `{level: name}` shape describes Neo4j's per-project SUMMARY indexes. This
    backend deliberately has neither — see the adapter docstring. What must hold regardless
    is that calling it twice changes nothing and that no name it returns is project-scoped.
    """
    proj = "11111111-1111-1111-1111-111111111111"
    model = "22222222-2222-2222-2222-222222222222"
    first = await store.ensure_index(project_id=proj, embedding_model_uuid=model,
                                     embedding_dimension=_DIM)
    second = await store.ensure_index(project_id="99999999-9999-9999-9999-999999999999",
                                      embedding_model_uuid=model, embedding_dimension=_DIM)
    # A DIFFERENT project gets the SAME index. That is the point: one index per dim, not
    # one per project — the ~30 000-index scheme is what Phase 3 exists to end.
    assert first == second
    assert proj.replace("-", "") not in "".join(first.values())


# ── the reason this backend exists: the filter reaches the planner ───────────


def _scan_nodes(node: dict) -> list[dict]:
    """Every node that reads a relation, depth-first."""
    found = []
    if "Relation Name" in node:
        found.append(node)
    for child in node.get("Plans", []):
        found.extend(_scan_nodes(child))
    return found


def _nodes_filtering_on(node: dict, column: str) -> list[dict]:
    found = []
    for key in ("Filter", "Index Cond", "Recheck Cond"):
        if column in str(node.get(key, "")):
            found.append(node)
            break
    for child in node.get("Plans", []):
        found.extend(_nodes_filtering_on(child, column))
    return found


async def _seed_two_tenants(vector_pool, rows: int) -> None:
    """Enough rows that an index path is worth choosing, split evenly between two users.

    Asserts its own output is DISTINCT — see the correlation comment below. A seed that
    silently collapses to one repeated vector is invisible in every test that uses it.
    """
    async with vector_pool.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO {passage_table(_DIM)}
                (user_id, project_id, source_type, source_id, chunk_index, text,
                 embedding, embedding_model, canon)
            SELECT CASE WHEN g % 2 = 0 THEN $1 ELSE $2 END, $3, 'chapter', 'seed-' || g, 0,
                   'seeded row ' || g,
                   -- `+ 0 * g` CORRELATES the subquery, which is the whole point.
                   --
                   -- The first version of this said volatility was enough — "random() is
                   -- VOLATILE, so this is re-evaluated per outer row" — and it was WRONG.
                   -- An UNcorrelated subquery is hoisted into an InitPlan and evaluated
                   -- ONCE however volatile its body is, so the seed produced 3000 rows
                   -- holding ONE distinct vector (measured: `count(DISTINCT embedding)`
                   -- = 1). Every distance was then zero, every ranking arbitrary, and a
                   -- recall test built on this helper measured nothing at all while
                   -- looking fine.
                   --
                   -- `g` appears in generate_series' ARGUMENT, not inside the aggregate:
                   -- putting it inside raises "column g.g must appear in the GROUP BY".
                   (SELECT array_agg(random())::vector({_DIM})
                      FROM generate_series(1, {_DIM} + 0 * g)),
                   'model-a', true
            FROM generate_series(1, {rows}) g
            """,
            _USER, _OTHER_USER, _PROJECT,
        )
        await conn.execute(f"ANALYZE {passage_table(_DIM)}")
        distinct = await conn.fetchval(
            f"SELECT count(DISTINCT embedding::text) FROM {passage_table(_DIM)}"
        )
        assert distinct == rows, (
            f"seed produced {distinct} distinct vectors for {rows} rows — the subquery was "
            "hoisted again, and every test built on this helper is ranking identical points"
        )


async def test_the_tenant_filter_is_evaluated_by_the_scan_not_after_it(store, vector_pool):
    """**The T23 claim.** Neo4j's vector index cannot filter by tenant, so its adapter
    over-fetches 10x and discards afterwards; `oversample_factor` was kept off the port
    because it is that backend's compensation. Here the predicate must be evaluated by the
    node that READS the table — if it were applied by a node above the scan, this backend
    would be doing the same over-fetch with different syntax and the migration would have
    bought nothing.
    """
    await _seed_two_tenants(vector_pool, 4000)
    sql, params, applied = store.build_search_sql(
        scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM, k=10,
        filter=VectorFilter(project_id=_PROJECT),
    )
    assert "project" in applied and "canon" in applied

    async with vector_pool.acquire() as conn:
        raw = await conn.fetchval(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}", *params)
    plan = json.loads(raw)[0]["Plan"] if isinstance(raw, str) else raw[0]["Plan"]

    scans = _scan_nodes(plan)
    assert len(scans) == 1, f"expected one relation scan, got {[s['Node Type'] for s in scans]}"
    scan = scans[0]
    assert scan["Relation Name"] == passage_table(_DIM)

    filtering = _nodes_filtering_on(plan, "user_id")
    assert filtering, "no plan node filters on user_id at all — the predicate never arrived"
    assert filtering == [scan], (
        "user_id is filtered by "
        f"{[n['Node Type'] for n in filtering]} rather than by the scan node itself — "
        "rows for every tenant are being read and discarded above the scan, which is the "
        "Neo4j behaviour this backend was chosen to avoid"
    )
    # Real selectivity evidence rather than a guess, and the number the adapter's DEBUG line
    # is a cheap stand-in for.
    print(
        f"[T23] scan={scan['Node Type']} index={scan.get('Index Name', '-')} "
        f"rows_out={scan.get('Actual Rows')} removed_by_filter={scan.get('Rows Removed by Filter')}"
    )


async def test_the_diskann_index_is_usable_at_all(store, vector_pool):
    """The companion control. The test above proves WHERE the predicate is evaluated, which
    a sequential scan would also satisfy — it filters while reading, too. This one proves
    the approximate index is genuinely available for the ordering, so the two together mean
    "index path AND planner-side filtering" rather than either alone.
    """
    await _seed_two_tenants(vector_pool, 4000)
    async with vector_pool.acquire() as conn:
        raw = await conn.fetchval(
            f"EXPLAIN (COSTS OFF, FORMAT JSON) SELECT source_id FROM {passage_table(_DIM)} "
            f"ORDER BY embedding <=> $1::vector LIMIT 10",
            "[" + ",".join(repr(random.random()) for _ in range(_DIM)) + "]",
        )
    plan = json.loads(raw)[0]["Plan"] if isinstance(raw, str) else raw[0]["Plan"]
    used = {n.get("Index Name") for n in _scan_nodes(plan)}
    assert index_name("passage", _DIM, "emb") in used, (
        f"the planner ignored the diskann index (used {used or 'none'}) — it builds but "
        "does not serve, which no correctness test would notice"
    )


# ── include_vectors, against the real driver (T24b) ──────────────────────────


@pytest.mark.asyncio
async def test_include_vectors_returns_the_STORED_vector_and_off_returns_none(store):
    """🔴 **The fake cannot prove this one.** Postgres hands the column back through
    `embedding::text` and `_parse_vector` reads it, because asyncpg has no codec for
    pgvector's type — a round trip through a string that a fake, which just hands back the
    list it was given, never exercises at all. The failure it guards is a `vector` that
    arrives as the literal string `"[0.1,0.2]"`: perfectly truthy, and MMR's cosine then
    raises or silently scores garbage.

    Both directions, and the OFF direction is the expensive one: a store that always
    returned the vector would make every caller that never asked pay `k × dim` floats.
    """
    await store.upsert(_passage("with-vec", _axis(0)))

    off = await store.search(scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM, k=5)
    assert off and off[0].vector is None, (
        "a search that did not ask for vectors got one — the payload is now unconditional")

    on = await store.search(scope="passage", user_id=_USER, embedding=_axis(0), dim=_DIM,
                            k=5, include_vectors=True)
    assert on, "the seeded passage did not come back at all"
    got = on[0].vector
    assert isinstance(got, list) and len(got) == _DIM, (
        f"the stored vector came back as {type(got).__name__} — not parsed into floats, so "
        f"MMR's cosine sees a string")
    assert all(isinstance(x, float) for x in got), "the parsed vector holds non-floats"
    assert got == pytest.approx(_axis(0), abs=1e-5), (
        "the vector that came back is not the one that was stored")


@pytest.mark.asyncio
async def test_a_passage_hit_carries_the_columns_the_DRAWER_READ_publishes(store):
    """`project_id` and `created_at` are fields of the public `DrawerSearchHit` response.
    They were absent from this backend's projection, so a reader migrated onto the port
    would have had to DROP two fields from a shipped API to go through it — which reads to
    a client as "the server stopped sending them", not as a migration."""
    await store.upsert(_passage("published", _axis(0)))
    hit = (await store.search(scope="passage", user_id=_USER, embedding=_axis(0),
                              dim=_DIM, k=5))[0]
    assert hit.attributes["project_id"] == _PROJECT
    assert hit.attributes["created_at"] is not None, (
        "created_at came back NULL — the column exists but nothing defaults it")
    assert "block_index" in hit.attributes, "block_index is not projected"


@pytest.mark.asyncio
async def test_the_read_columns_are_ADDED_to_a_pre_t24b_table(vector_pool):
    """The same failure mode `test_entity_lifecycle_columns_are_added_to_a_pre_t25b_table`
    exists for: a column added to the CREATE TABLE appears on every fresh test database and
    on NO deployment that already has data. The search would then fail at runtime on exactly
    the installations that matter, having passed every test.

    So the old shape is reconstructed and `ensure_vector_schema` is asked to fix it.
    """
    table = passage_table(_DIM)
    async with vector_pool.acquire() as conn:
        await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        # A pre-T24b passage table: no created_at, no block_index.
        await conn.execute(
            f"CREATE TABLE {table} ("
            f"  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
            f"  user_id text NOT NULL, project_id text,"
            f"  source_type text NOT NULL, source_id text NOT NULL,"
            f"  chunk_index integer NOT NULL, text text NOT NULL,"
            f"  embedding vector({_DIM}) NOT NULL, embedding_model text,"
            f"  is_hub boolean NOT NULL DEFAULT false, chapter_index integer,"
            f"  canon boolean NOT NULL DEFAULT true,"
            f"  source_lang text NOT NULL DEFAULT 'unknown',"
            f"  mixed boolean NOT NULL DEFAULT false, content_hash text,"
            f"  updated_at timestamptz NOT NULL DEFAULT now(),"
            f"  UNIQUE (user_id, source_type, source_id, chunk_index))"
        )

    await ensure_vector_schema(vector_pool, dims=(_DIM, _OTHER_DIM))

    async with vector_pool.acquire() as conn:
        cols = {
            r["column_name"] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
                table,
            )
        }
    assert {"created_at", "block_index"} <= cols, (
        f"ensure_vector_schema left a pre-T24b table unmigrated: has {sorted(cols)}")

    # And the projection actually works against the migrated table, which is the thing the
    # column check alone does not prove.
    store = PgVectorStore(vector_pool)
    await store.upsert(_passage("after-migrate", _axis(0)))
    hit = (await store.search(scope="passage", user_id=_USER, embedding=_axis(0),
                              dim=_DIM, k=5))[0]
    assert hit.attributes["created_at"] is not None
