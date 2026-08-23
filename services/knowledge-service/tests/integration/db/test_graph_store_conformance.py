"""GraphStore CONFORMANCE — the same rules, run against every adapter (plan T42a).

WHY THIS EXISTS, and it is a gap rather than an improvement
-----------------------------------------------------------
`tests/unit/test_graph_store_port.py` is described as the port's contract. Measured
2026-08-12 it holds **14 `FakeGraphStore()` instantiations and ZERO of
`Neo4jGraphStore`**. The one test that names the real adapter,
`test_implementations_match_the_port_signatures`, compares `inspect.signature` —
parameter names, kinds and defaults. **Purely structural.**

So before this file, an adapter could satisfy every existing test by declaring the right
signatures and behaving arbitrarily. That is not a hypothetical for this plan: **T42 adds
an AGE adapter and T43 diffs it against Neo4j.** A shadow comparison between two adapters
that were never checked against the port's semantics measures *agreement*, not
correctness — and two implementations can agree by sharing a bug. This suite is the
correctness baseline T43 stands on.

It is the same vacuity class the plan has already hit twice: `D-T38-MECHANISM-IS-VACUOUS`
(two green gates that excluded T38's whole scope) and the SQ3 audit (gates wired to CI
with no proof they can go red).

WHAT IS ENFORCED, AND WHY THESE RULES
-------------------------------------
The rules whose violation is **SILENT** — nothing raises, a query just answers wrong:

  * idempotency of the resolver          — a duplicate-minting bug the KG has shipped before
  * project isolation                    — two books' casts merging
  * tenant isolation on read AND on write — a cross-user read, and an archive that writes
                                            to another user's node
  * archived entities excluded by default — a resolver re-anchoring extraction onto an
                                            entity the author archived
  * the half-open `as_of` interval        — off-by-one at the boundary chapter
  * positionless edges excluded from a timed read, present in a head read
  * direction and confidence filtering    — an unfiltered edge reaching a canon check

THE SKIP IS THE DANGER, SO IT IS GATED
--------------------------------------
`AGENTS.md` records the trap directly: *env-gated integration tests skip and the green
suite lies.* A conformance suite that silently degrades to fake-only is worse than none,
because it reports the word "conformance" while proving nothing about any real store.

So `test_a_real_adapter_actually_ran` **fails** when `CONFORMANCE_REQUIRE_REAL=1` and only
the fake was exercised. CI sets it; a laptop without a throwaway Neo4j does not, and there
the suite still runs every rule against the fake. The skip stays visible either way — the
adapter list is asserted, not assumed.

    # fake only (no Neo4j needed)
    pytest tests/integration/db/test_graph_store_conformance.py

    # + the real adapter, against a THROWAWAY graph (never :7687/:7688 — the fixture refuses)
    docker run -d --name lw-neo4j-scratch -p 7999:7687 \
      -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community
    TEST_NEO4J_URI=bolt://localhost:7999 CONFORMANCE_REQUIRE_REAL=1 \
      pytest tests/integration/db/test_graph_store_conformance.py
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.adapters.fake_graph_store import FakeGraphStore
from app.adapters.neo4j_graph_store import Neo4jGraphStore

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Which adapters this process actually exercised. Asserted at the end rather than trusted:
# the whole failure mode being defended against is a suite that quietly ran nothing real.
_EXERCISED: set[str] = set()


def _ids() -> tuple[str, str, str]:
    """Fresh user/project/other-user per test.

    Neo4j community has no TRUNCATE and the shared-graph guard only refuses the DEV ports,
    so a throwaway can still carry residue from an earlier run. Unique ids make each test
    independent of what is already in the store — which a fake never needs and a real
    adapter always does. Getting this wrong produces a suite that passes alone and fails
    in a batch, i.e. the flakiness that gets conformance suites disabled.
    """
    n = uuid.uuid4().hex[:12]
    return f"u-{n}", f"p-{n}", f"other-{n}"


# ── the adapters under test ──────────────────────────────────────────────────


@pytest_asyncio.fixture(params=["fake", "neo4j", "age", "kuzu"])
async def store(request):
    """One GraphStore per param. `fake` always runs; `neo4j` skips only its own param when
    no throwaway is configured — and that skip is what `test_a_real_adapter_actually_ran`
    refuses to let pass silently in CI.

    ⚠️ The driver is built HERE rather than delegated to the `neo4j_driver` fixture, and
    both halves of that are deliberate. Requesting `neo4j_driver` directly would fire its
    `pytest.skip` during setup of the **fake** parameter too, silently halving the suite —
    a conformance run that skips half of itself while reporting green. Wrapping it in
    another async fixture and reaching for `request.getfixturevalue` does not work either:
    pytest tries to resolve the async fixture synchronously and every test errors with
    *"Runner.run() cannot be called from a running event loop"* (measured — it took the
    whole suite down on the first real run).

    The throwaway guard is imported rather than re-implemented, so there is ONE definition
    of "this is not the dev graph".
    """
    if request.param == "fake":
        _EXERCISED.add("fake")
        fake = FakeGraphStore()
        # The fake has no ExtractionSource concept; evidence attaches by id alone. It must
        # still be AWAITABLE — the rule awaits this uniformly across adapters.
        async def _mk_fake_source(_u, _sid):
            return None

        fake._mk_source = _mk_fake_source                 # type: ignore[attr-defined]

        async def _set_fake_glossary(u, eid, gid):
            fake._entities[eid].glossary_entity_id = gid

        fake._set_glossary = _set_fake_glossary           # type: ignore[attr-defined]
        yield fake
        return

    if request.param == "age":
        dsn = os.environ.get("TEST_AGE_DSN")
        if not dsn:
            pytest.skip("TEST_AGE_DSN not set — the AGE adapter is not being conformed")
        from app.adapters.age_graph_store import AgeGraphStore
        from app.db.age_bootstrap import create_age_pool, ensure_graph

        # One graph per test run, not per project: these rules are about tenancy WITHIN a
        # graph, and putting each test in its own graph would make the user_id predicates
        # pass for the wrong reason — isolation by container rather than by the filter the
        # adapter is supposed to apply.
        pool = await create_age_pool(dsn, min_size=2, max_size=4)
        try:
            async with pool.acquire() as conn:
                gname = await ensure_graph(conn, uuid.uuid4())
            _EXERCISED.add("age")
            age = AgeGraphStore(pool, gname)

            async def _mk_age_source(u, sid):
                await age._run(
                    f"MERGE (s:ExtractionSource {{id: '{sid}', user_id: '{u}'}}) RETURN s")

            age._mk_source = _mk_age_source                # type: ignore[attr-defined]

            async def _set_age_glossary(u, eid, gid):
                await age._run(
                    f"MATCH (e:Entity {{id: '{eid}', user_id: '{u}'}}) "
                    f"SET e.glossary_entity_id = '{gid}' RETURN e")

            age._set_glossary = _set_age_glossary          # type: ignore[attr-defined]
            yield age
        finally:
            await pool.close()
        return

    if request.param == "kuzu":
        pytest.importorskip("kuzu", reason="kuzu is an optional T43-candidate dependency")
        from app.adapters.kuzu_graph_store import KuzuGraphStore
        from app.db.kuzu_bootstrap import close_kuzu, open_kuzu

        # A directory per test rather than a shared one, and that is not the usual isolation
        # shortcut: Kuzu is EMBEDDED and one process may hold one handle per path, so a shared
        # database would make the second test fail with `Could not set lock on file`. The
        # tenancy rules still discriminate because they filter on user_id within the store.
        tmp = tempfile.mkdtemp(prefix="kuzu-conformance-")
        db, conn = open_kuzu(os.path.join(tmp, "kg"))
        try:
            _EXERCISED.add("kuzu")
            kz = KuzuGraphStore(conn)

            async def _mk_kuzu_source(u, sid):
                # Really creates it, as the AGE branch does. It was a no-op while the adapter
                # silently minted missing sources; now that `add_evidence` correctly treats an
                # absent source as a MISS (matching Neo4j), a no-op here would make the rule
                # fail for the fixture's reason rather than the adapter's.
                await kz._run(
                    "MERGE (s:ExtractionSource {id: $s}) ON CREATE SET s.user_id = $u",
                    {"s": sid, "u": u})

            kz._mk_source = _mk_kuzu_source            # type: ignore[attr-defined]

            async def _set_kuzu_glossary(u, eid, gid):
                await kz._run(
                    "MATCH (e:Entity {id: $i}) SET e.glossary_entity_id = $g",
                    {"i": eid, "g": gid})

            kz._set_glossary = _set_kuzu_glossary      # type: ignore[attr-defined]
            yield kz
        finally:
            close_kuzu(db, conn)
            shutil.rmtree(tmp, ignore_errors=True)
        return

    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        pytest.skip("TEST_NEO4J_URI not set — the real adapter is not being conformed")

    from neo4j import AsyncGraphDatabase

    from .conftest import _guard_throwaway_neo4j

    _guard_throwaway_neo4j(uri)
    driver = AsyncGraphDatabase.driver(
        uri,
        auth=(os.environ.get("TEST_NEO4J_USER", "neo4j"),
              os.environ.get("TEST_NEO4J_PASSWORD", "loreweave_dev_neo4j")),
        connection_timeout=5.0,
    )
    try:
        await driver.verify_connectivity()
        async with driver.session() as session:
            _EXERCISED.add("neo4j")
            n4j = Neo4jGraphStore(session)

            async def _mk_neo_source(u, sid):
                await session.run(
                    "MERGE (s:ExtractionSource {id: $sid, user_id: $u}) RETURN s",
                    {"sid": sid, "u": u})

            n4j._mk_source = _mk_neo_source                # type: ignore[attr-defined]

            async def _set_neo_glossary(u, eid, gid):
                await session.run(
                    "MATCH (e:Entity {id: $i, user_id: $u}) SET e.glossary_entity_id = $g",
                    {"i": eid, "u": u, "g": gid})

            n4j._set_glossary = _set_neo_glossary          # type: ignore[attr-defined]
            yield n4j
    finally:
        await driver.close()


# ── entities ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolving_the_same_name_twice_returns_the_same_entity(store):
    u, p, _ = _ids()
    a = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    b = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chat")
    assert a.id == b.id
    # Load-bearing: source types ACCUMULATE. A matching id survives an adapter that builds
    # a fresh object at the same key; only this shows the EXISTING entity was returned and
    # updated, which is what idempotent means here.
    assert sorted(b.source_types) == ["chapter", "chat"]


@pytest.mark.asyncio
async def test_the_merge_arm_ADVANCES_the_version(store):
    """T17 A24 — OCC is a port-level promise and nothing conformed it.

    `Entity.version` is the optimistic-concurrency token. The AGE adapter never wrote it at
    all (A23): every entity came back with `version = NULL`, and a read-side coalesce turned
    that into a plausible `1`. The suite could not catch it because no rule looked — the rules
    for this method asserted id-stability, `source_types` accumulation and isolation, and
    stopped there.

    A create-then-merge on the same identity tuple is the smallest thing that can tell an
    adapter which maintains the token from one which returns a constant.
    """
    u, p, _ = _ids()
    a = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    b = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chat")
    assert a.id == b.id, "precondition: this must be the MERGE arm, not a second node"
    assert b.version > a.version, (
        f"version did not advance across the merge ({a.version} -> {b.version}). A token that "
        f"never moves cannot detect a concurrent write, and a read-side default makes an "
        f"unwritten one look correct."
    )


@pytest.mark.asyncio
async def test_auto_created_is_carried_and_a_real_extraction_CLAIMS_the_node(store):
    """The second half of A23, and it is not merely 'the flag round-trips'.

    `auto_created=False` from a later call is a REAL extraction claiming a node an earlier
    auto-creation minted, which the Neo4j writer documents as its own CASE arm. An adapter
    that stored the first value and never updated it would pass a round-trip assertion and
    fail this one.
    """
    u, p, _ = _ids()
    a = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter",
        auto_created=True)
    assert a.auto_created is True, "the port declares this parameter; it must reach the store"
    b = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chat",
        auto_created=False)
    assert b.id == a.id
    assert b.auto_created is False, (
        "a later auto_created=False is a real extraction claiming the node — an adapter that "
        "keeps the first value passes a round-trip check and loses this"
    )


@pytest.mark.asyncio
async def test_a_returned_entity_is_a_SNAPSHOT_not_a_live_handle(store):
    """A store returns a value, not a window onto its own state.

    The in-memory double returned the object it had stored, on BOTH arms. Every before/after
    assertion in every test using it was therefore comparing one object with itself — the
    version rule above read `2 > 2` and failed for a reason that had nothing to do with
    versioning. A real store cannot do this; a double that does is not modelling one.

    Mutating what came back must not reach the store, and the merge arm needs its own check:
    with only the create arm fixed, `a` is already frozen and the version rule passes while
    the merge arm still leaks.
    """
    u, p, _ = _ids()
    a = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    a.name = "MUTATED-ON-THE-CREATE-ARM"
    b = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chat")
    assert b.name != "MUTATED-ON-THE-CREATE-ARM", (
        "the create arm handed back a live handle: a caller's edit reached the store"
    )
    b.name = "MUTATED-ON-THE-MERGE-ARM"
    c = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    assert c.name != "MUTATED-ON-THE-MERGE-ARM", (
        "the MERGE arm handed back a live handle — the arm the version rule cannot reach, "
        "because by then the caller's first object is already a frozen snapshot"
    )


@pytest.mark.asyncio
async def test_the_same_name_in_two_projects_is_two_entities(store):
    u, p, _ = _ids()
    a = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    b = await store.resolve_or_merge_entity(
        user_id=u, project_id=f"{p}-second", name="Kai", kind="character",
        source_type="chapter")
    assert a.id != b.id


@pytest.mark.asyncio
async def test_another_users_entity_is_not_found_by_name(store):
    u, p, other = _ids()
    await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    assert await store.find_entities_by_name(
        user_id=other, project_id=p, name="Kai") == []


@pytest.mark.asyncio
async def test_an_archived_entity_is_excluded_from_name_resolution_by_default(store):
    u, p, _ = _ids()
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    await store.archive_entity(user_id=u, canonical_id=e.id, reason="test")
    assert await store.find_entities_by_name(user_id=u, project_id=p, name="Kai") == []
    included = await store.find_entities_by_name(
        user_id=u, project_id=p, name="Kai", include_archived=True)
    assert [x.id for x in included] == [e.id]


@pytest.mark.asyncio
async def test_archiving_another_users_entity_is_a_miss_not_a_write(store):
    """The dangerous half is the WRITE. A tenancy check that only filters the return value
    would still have archived the row."""
    u, p, other = _ids()
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    assert await store.archive_entity(
        user_id=other, canonical_id=e.id, reason="test") is None
    still = await store.find_entities_by_name(user_id=u, project_id=p, name="Kai")
    assert [x.id for x in still] == [e.id], "another user's archive took effect"


@pytest.mark.asyncio
async def test_restore_undoes_an_archive(store):
    u, p, _ = _ids()
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    await store.archive_entity(user_id=u, canonical_id=e.id, reason="test")
    await store.restore_entity(user_id=u, canonical_id=e.id)
    assert [x.id for x in await store.find_entities_by_name(
        user_id=u, project_id=p, name="Kai")] == [e.id]


# ── relations ────────────────────────────────────────────────────────────────


async def _pair(store, u, p):
    a = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    b = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Mira", kind="character", source_type="chapter")
    return a, b


@pytest.mark.asyncio
async def test_as_of_respects_the_interval_start(store):
    """`valid_from_ordinal <= N` — an edge is not visible before the position it was
    established at.

    ⚠️ **The UPPER bound is not conformable through this port, and that is a finding, not
    an omission here.** `upsert_relation` accepts `valid_from_ordinal` and has **no
    `valid_to_ordinal`**: the port can OPEN a story interval and cannot CLOSE one. The
    half-open convention `valid_from <= N < valid_to` is documented on `relations_for`, so
    an adapter must implement an upper bound that no port caller can produce — and no
    conformance test can therefore check it on the write path.

    That matters precisely because closing intervals is what T36 was about: 175 relations
    that had already ENDED were being served as currently true. A second adapter could get
    the upper bound wrong and this suite would not see it. Recorded as
    `D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL`.
    """
    u, p, _ = _ids()
    a, b = await _pair(store, u, p)
    await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="ally_of",
        confidence=0.9, valid_from_ordinal=10)

    assert not await store.relations_for(user_id=u, entity_id=a.id, as_of=9), \
        "an edge established at 10 must not be visible at 9"
    assert await store.relations_for(user_id=u, entity_id=a.id, as_of=10), \
        "the lower bound is INCLUSIVE — the establishing position is covered"
    assert await store.relations_for(user_id=u, entity_id=a.id, as_of=999)


@pytest.mark.asyncio
async def test_a_positionless_edge_is_excluded_by_a_timed_read_but_not_by_a_head_read(store):
    """An edge with no story position cannot be placed, so a timed answer must not claim
    it. It must still exist for an untimed read, or authoring loses it silently."""
    u, p, _ = _ids()
    a, b = await _pair(store, u, p)
    await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="knows", confidence=0.9)
    assert not await store.relations_for(user_id=u, entity_id=a.id, as_of=5)
    assert await store.relations_for(user_id=u, entity_id=a.id)


@pytest.mark.asyncio
async def test_low_confidence_edges_are_filtered_by_default(store):
    u, p, _ = _ids()
    a, b = await _pair(store, u, p)
    await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="maybe_knows",
        confidence=0.05)
    assert not await store.relations_for(user_id=u, entity_id=a.id)
    assert await store.relations_for(user_id=u, entity_id=a.id, min_confidence=0.0)


@pytest.mark.asyncio
async def test_an_edge_to_an_ARCHIVED_peer_is_excluded(store):
    """An archived entity's edges must not surface through a live entity's neighbourhood.

    🐞 **Added 2026-08-12 because the AGE adapter got this wrong and this suite did not
    notice.** T43's property-based differential run found it (seed=1): after an archive, AGE
    returned an edge Neo4j did not —
        primary  =[('parent_of','0.85','12')]
        secondary=[('ally_of','0.7','5'), ('parent_of','0.85','12')]
    Nine green conformance operations had said nothing about it, because no rule here
    archived a peer and then read relations.

    That is the lesson worth more than the fix: **the conformance suite is the correctness
    baseline, so a rule the differential run discovers belongs HERE**, or the next adapter
    re-learns it the same way. The consequence is user-visible — a relation to an entity the
    author deliberately archived, presented as current.
    """
    u, p, _ = _ids()
    a, b = await _pair(store, u, p)
    await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="ally_of", confidence=0.9)
    assert await store.relations_for(user_id=u, entity_id=a.id), "fixture edge missing"

    await store.archive_entity(user_id=u, canonical_id=b.id, reason="test")
    assert await store.relations_for(user_id=u, entity_id=a.id) == [], (
        "an edge to an ARCHIVED peer was returned — the author removed that entity, and a "
        "caller would render a relation to something that is supposed to be gone"
    )


@pytest.mark.asyncio
async def test_another_users_relations_are_not_returned(store):
    u, p, other = _ids()
    a, b = await _pair(store, u, p)
    await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="ally_of", confidence=0.9)
    assert await store.relations_for(user_id=other, entity_id=a.id) == []


# ── the control that makes the rest mean anything ────────────────────────────


def test_a_real_adapter_actually_ran():
    """A conformance suite that degraded to fake-only would report the word "conformance"
    while proving nothing about any real store — the exact shape of
    `env-gated-integration-tests-skip-and-the-green-suite-lies`.

    So the adapter set is ASSERTED. CI sets `CONFORMANCE_REQUIRE_REAL=1`; a laptop without
    a throwaway Neo4j does not, and there the rules still run against the fake.
    """
    assert "fake" in _EXERCISED, "the fake did not run — the suite did not execute"
    if os.environ.get("CONFORMANCE_REQUIRE_REAL") == "1":
        real = _EXERCISED - {"fake"}
        assert real, (
            "CONFORMANCE_REQUIRE_REAL=1 but only the fake was exercised. Set TEST_NEO4J_URI "
            "to a THROWAWAY graph (the fixture refuses :7687/:7688). A green run here "
            "without a real adapter is the lie this assertion exists to prevent."
        )


# ── evidence: the port's newest operation (T17, grown by demand) ─────────────


@pytest.mark.asyncio
async def test_evidence_is_idempotent_on_the_job_and_bumps_the_counter(store):
    """`add_evidence` must be idempotent on `(target, source, job_id)`.

    ⚠️ **The atomic counter is the invariant, not the edge.** Re-running one extraction job
    is a no-op against `evidence_count`; an adapter that incremented per call would inflate
    every entity's evidence on every retry, and the K11.9 reconciler is only the offline net
    that catches that drift. Never producing it is the cheaper path — so the rule lives here,
    where all three adapters must satisfy it.
    """
    u, p, _ = _ids()
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    src = f"src-{uuid.uuid4().hex[:10]}"
    job = f"job-{uuid.uuid4().hex[:8]}"

    # ⚠️ The source node is CREATED rather than skipped over. An earlier cut of this test
    # skipped when `add_evidence` returned None for want of an `:ExtractionSource`, which
    # meant the idempotency rule ran on the FAKE only — the engines it exists to constrain
    # were the two being skipped. That is the env-gated-skip trap inside a conformance suite.
    await store._mk_source(u, src)

    first = await store.add_evidence(
        user_id=u, target_label="Entity", target_id=e.id, source_id=src,
        extraction_model="m1", confidence=0.9, job_id=job)
    assert first is not None, "the source node was created but add_evidence still returned None"

    second = await store.add_evidence(
        user_id=u, target_label="Entity", target_id=e.id, source_id=src,
        extraction_model="m1", confidence=0.9, job_id=job)

    assert second is not None
    assert second.evidence_count == first.evidence_count, (
        f"re-running one job moved evidence_count {first.evidence_count} -> "
        f"{second.evidence_count}: the counter drifts on every retry"
    )
    assert second.created is False, "the second call reported a NEW edge"


@pytest.mark.asyncio
async def test_evidence_rejects_the_same_caller_errors_everywhere(store):
    """A port whose implementations disagree about what is a CALLER error leaks its engine.

    An empty `job_id` is what makes the operation idempotent, so accepting one is not a
    lenient convenience — it silently removes the idempotency key. All three adapters must
    refuse it identically.
    """
    u, p, _ = _ids()
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    with pytest.raises(ValueError):
        await store.add_evidence(
            user_id=u, target_label="Entity", target_id=e.id, source_id="s1",
            extraction_model="m1", confidence=0.9, job_id="")
    with pytest.raises(ValueError):
        await store.add_evidence(
            user_id=u, target_label="Entity", target_id=e.id, source_id="s1",
            extraction_model="m1", confidence=9.0, job_id="j1")


# ── relation corrections: the port's newest operations (T17 A1) ──────────────


@pytest.mark.asyncio
async def test_get_relation_finds_it_and_is_a_MISS_for_another_user(store):
    """`None` must be a miss, not an error and not another user's row. Both halves matter:
    returning the row leaks across tenants, raising would be an existence oracle."""
    u, p, other = _ids()
    a, b = await _pair(store, u, p)
    made = await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="ally_of", confidence=0.9)

    got = await store.get_relation(user_id=u, relation_id=made.id)
    assert got is not None and got.id == made.id
    assert await store.get_relation(user_id=other, relation_id=made.id) is None


@pytest.mark.asyncio
async def test_invalidate_hides_the_edge_from_ordinary_reads_and_is_idempotent(store):
    """A correction that errors on a repeat cannot be retried after a timeout, so the
    second call must succeed too."""
    u, p, _ = _ids()
    a, b = await _pair(store, u, p)
    made = await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="ally_of", confidence=0.9)
    assert len(await store.relations_for(user_id=u, entity_id=a.id)) == 1

    assert await store.invalidate_relation(user_id=u, relation_id=made.id) is not None
    assert await store.relations_for(user_id=u, entity_id=a.id) == [], (
        "an invalidated edge is still served by the default read"
    )
    assert await store.invalidate_relation(user_id=u, relation_id=made.id) is not None, (
        "re-invalidating failed — the correction is not retryable"
    )


@pytest.mark.asyncio
async def test_recreate_RESURRECTS_an_invalidated_edge_rather_than_duplicating_it(store):
    """The rule the whole primitive exists for (F5). If the adapter matched on
    `valid_until IS NULL` — as `upsert_relation` does — it would mint a SECOND edge beside
    the invalidated one, the author's correction would appear to work, and the graph would
    carry two arcs for one relationship. That failure is invisible from the read side,
    which returns exactly one edge either way."""
    u, p, _ = _ids()
    a, b = await _pair(store, u, p)
    made = await store.upsert_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="ally_of", confidence=0.9)
    await store.invalidate_relation(user_id=u, relation_id=made.id)

    revived = await store.recreate_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="ally_of",
        valid_from_ordinal=7)
    assert revived is not None
    assert revived.valid_until is None, "recreate did not clear valid_until"
    assert revived.confidence == 1.0, "an authored edge is not confidence 1.0"

    # ⚠️ Counting LIVE edges cannot detect the duplicate — it hides behind the very filter
    # that hides the invalidated original, so `len(live) == 1` holds whether recreate revived
    # the edge or minted a second one beside it. The first cut of this test asserted exactly
    # that and stayed GREEN under the mutation it existed to catch; the bite is what found it.
    #
    # `get_relation` is the one port read that can SEE an invalidated edge, so it is the only
    # probe that discriminates: if the original row is still invalid, recreate duplicated.
    original = await store.get_relation(user_id=u, relation_id=made.id)
    assert original is not None, "the original edge vanished — recreate deleted rather than revived"
    assert original.valid_until is None, (
        "recreate DUPLICATED the arc: the original row is still invalidated, so the author's "
        "correction created a second edge beside it instead of reviving this one"
    )
    live = await store.relations_for(user_id=u, entity_id=a.id)
    assert len(live) == 1, f"expected exactly one live edge, got {len(live)}"


@pytest.mark.asyncio
async def test_an_authored_relation_carries_its_story_position(store):
    """T36's binding constraint, as a rule. An authored relation with no
    `valid_from_ordinal` is positionless and invisible to every as-of read — which is
    exactly how T36's roles were authored and then could not be found."""
    u, p, _ = _ids()
    a, b = await _pair(store, u, p)
    await store.recreate_relation(
        user_id=u, subject_id=a.id, object_id=b.id, predicate="serves",
        valid_from_ordinal=12)

    assert len(await store.relations_for(user_id=u, entity_id=a.id, as_of=12)) == 1
    assert await store.relations_for(user_id=u, entity_id=a.id, as_of=11) == []


# ── event corrections (T17 A2) ───────────────────────────────────────────────

#: AGE refuses the two event WRITES (D-AGE-EVENT-WRITE-UNIMPLEMENTED). The refusal is
#: itself asserted below, so "AGE is skipped here" can never quietly become "AGE passed".
# T58 (2026-08-22): EMPTY. `D-AGE-EVENT-WRITE-UNIMPLEMENTED` claimed the ON MATCH branch
# had "no APOC-free AGE equivalent"; T57/T58 measured that the list union is a plain
# Cypher list comprehension AGE accepts, so `merge_event` and `update_event_fields` are
# implemented and the five skips below became assertions. Kept as a set rather than
# deleted: it is the mechanism by which a future refusal stays VISIBLE instead of being
# a silently-passing adapter, and the guard test below pins that it is honest either way.
_EVENT_WRITE_REFUSERS: set[str] = set()




def _which(store) -> str:
    """Which adapter this parameterisation is, by CLASS — not by a marker attribute the
    fixture would have to remember to set."""
    return {"AgeGraphStore": "age", "Neo4jGraphStore": "neo4j",
            "FakeGraphStore": "fake", "KuzuGraphStore": "kuzu"}[type(store).__name__]


async def _an_event(store, u, p, title="The Betrayal", **kw):
    return await store.merge_event(
        user_id=u, project_id=p, title=title, chapter_id="ch-1",
        source_type="chapter", **kw)


@pytest.mark.asyncio
async def test_a_re_mention_UNION_MERGES_participants_instead_of_replacing_them(store):
    """`merge_event`'s multi-source contract says participants union-merge with no duplicates,
    and until 2026-08-22 **no rule asserted it on any adapter**.

    The gap was found by a BITE, not by reading: mutating the AGE adapter to overwrite the
    stored list instead of unioning it selected no test at all. A semantic three adapters are
    required to share, with nothing pinning it, is the shape `_EVENT_WRITE_REFUSERS` exists to
    make impossible one level up.

    Replacement is the dangerous direction and it is silent: chapter 2 re-mentions the event
    naming only Kai, and Mei — extracted from chapter 1 — disappears from the event with no
    error, no log, and a perfectly plausible-looking row.
    """
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_event_writes")
    u, p, _ = _ids()
    first = await _an_event(store, u, p, participants=["Mei", "Kai"])
    assert sorted(first.participants) == ["Kai", "Mei"], (
        "the create path lost a participant before any merge happened"
    )
    # Overlapping, not disjoint: 'Kai' must not appear twice, which is what tells a union
    # apart from a concatenation. A disjoint second mention passes under both.
    second = await _an_event(store, u, p, participants=["Kai", "Rin"])
    assert second.id == first.id, "merge_event minted a second node for the same key"
    assert sorted(second.participants) == ["Kai", "Mei", "Rin"], (
        f"participants are {second.participants!r} — a re-mention must UNION: 'Mei' came "
        f"from the earlier mention and must survive, and 'Kai' must not be duplicated"
    )

    # An EMPTY mention must not wipe the list either. `merge_event` treats "no participants
    # supplied" as no new information, not as a deliberate clear — the same reason `summary`
    # normalizes "" to None.
    third = await _an_event(store, u, p, participants=[])
    assert sorted(third.participants) == ["Kai", "Mei", "Rin"], (
        f"an empty participants list CLEARED the stored ones ({third.participants!r}) — "
        f"a mention that names nobody is silence, not an erasure"
    )


@pytest.mark.asyncio
async def test_merge_event_is_idempotent_and_keeps_the_EARLIEST_reading_position(store):
    """CM4 spoiler-safety, as a rule. `event_order` keeps the MINIMUM across mentions: an
    event re-mentioned in chapter 40 must not migrate forward and become invisible to a
    reader at chapter 12. An adapter taking the latest leaks nothing and hides everything —
    silent in both directions, which is why it is pinned rather than described."""
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_event_writes")
    # ⚠️ The ORDER of these two mentions is the whole test. Mentioning 40k first and 12k
    # second cannot discriminate: min-wins and latest-wins both end at 12k. The first cut did
    # exactly that and stayed GREEN under the latest-wins mutation — found by the bite, not by
    # reading. The early mention must come FIRST, so only min-wins keeps it.
    u, p, _ = _ids()
    a = await _an_event(store, u, p, event_order=12_000)
    b = await _an_event(store, u, p, event_order=40_000)
    assert a.id == b.id, "merge_event minted a second node for the same (user, chapter, title)"
    assert b.event_order == 12_000, (
        f"event_order went FORWARD to {b.event_order} — a later mention hid the event from "
        "readers who have already passed it"
    )


@pytest.mark.asyncio
async def test_a_thinner_re_mention_does_not_erase_a_richer_summary(store):
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_event_writes")
    u, p, _ = _ids()
    await _an_event(store, u, p, summary="Kai betrays Mira at the gate.")
    again = await _an_event(store, u, p, summary=None)
    assert again.summary == "Kai betrays Mira at the gate.", (
        "a re-mention with no summary overwrote the one already stored"
    )


@pytest.mark.asyncio
async def test_get_event_is_a_MISS_for_another_user(store):
    """Read side of the tenancy rule — available on every adapter, including the one that
    refuses the writes."""
    u, p, other = _ids()
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("needs merge_event to create the row — AGE refuses it")
    ev = await _an_event(store, u, p)
    assert (await store.get_event(user_id=u, event_id=ev.id)) is not None
    assert (await store.get_event(user_id=other, event_id=ev.id)) is None


@pytest.mark.asyncio
async def test_a_stale_expected_version_RAISES_rather_than_silently_losing_the_edit(store):
    """The OCC rule. A lost update that reports success is indistinguishable from a saved
    one to the caller who just overwrote somebody else's edit — so this must raise, and
    an adapter that returned `(None, None)` on a version clash would be reporting a MISS
    for a row that exists."""
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_event_writes")
    from app.db.repositories import VersionMismatchError

    u, p, _ = _ids()
    ev = await _an_event(store, u, p)
    # Snapshot the title NOW. The in-memory fake returns the LIVE object and mutates it in
    # place, so `ev.title` becomes the new title after the update; the Neo4j adapter returns
    # a fresh projection and does not. Comparing against `ev.title` afterwards passes on one
    # adapter and fails on the other for a reason that has nothing to do with the rule.
    original_title, original_version = ev.title, ev.version
    updated, before = await store.update_event_fields(
        user_id=u, event_id=ev.id, title="Corrected title", summary=None,
        time_cue=None, event_date_iso=None, expected_version=original_version)
    assert updated is not None and updated.title == "Corrected title"
    assert before is not None and before["title"] == original_title, (
        "the pre-edit snapshot is missing — the correction event has nothing to record"
    )

    with pytest.raises(VersionMismatchError):
        await store.update_event_fields(
            user_id=u, event_id=ev.id, title="Racing edit", summary=None,
            time_cue=None, event_date_iso=None, expected_version=original_version)


@pytest.mark.asyncio
async def test_archive_event_is_idempotent(store):
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("needs merge_event to create the row — AGE refuses it")
    u, p, _ = _ids()
    ev = await _an_event(store, u, p)
    first = await store.archive_event(user_id=u, event_id=ev.id)
    assert first is not None and first.archived_at is not None
    assert await store.archive_event(user_id=u, event_id=ev.id) is not None, (
        "re-archiving failed — the correction is not retryable after a timeout"
    )


@pytest.mark.asyncio
async def test_the_event_write_REFUSERS_SET_is_honest_in_BOTH_directions(store):
    """`_EVENT_WRITE_REFUSERS` must describe reality, whichever way it points.

    ⚠️ **Rewritten 2026-08-22 (T58) because emptying the set made the old version
    unfailable.** It read `if _which(store) not in _EVENT_WRITE_REFUSERS: skip` — correct while
    AGE refused, and a permanent skip for every adapter the moment AGE stopped. A test that
    skips on all four parameters still prints as coverage, which is precisely the shape it was
    written to prevent, one level up.

    So it now asserts the set both ways:

    * a listed adapter must REALLY raise — otherwise the set is a way to hide a silent no-op,
      the suite reporting green for three adapters while one does nothing;
    * an UNLISTED adapter must really implement it — otherwise a `NotImplementedError`
      re-appearing (a bad rebase, a half-finished refactor) would turn five behavioural rules
      into five silent passes without anyone editing this file.

    The second half is what has teeth today, and it is what the old version could not say.
    """
    u, p, _ = _ids()
    listed = _which(store) in _EVENT_WRITE_REFUSERS
    if listed:
        with pytest.raises(NotImplementedError, match="D-AGE-EVENT-WRITE-UNIMPLEMENTED"):
            await store.merge_event(user_id=u, project_id=p, title="X", chapter_id="ch-1")
        with pytest.raises(NotImplementedError, match="D-AGE-EVENT-WRITE-UNIMPLEMENTED"):
            await store.update_event_fields(
                user_id=u, event_id="x", title=None, summary=None, time_cue=None,
                event_date_iso=None, expected_version=1)
        return

    # Not listed ⇒ it must actually work. `NotImplementedError` is the only failure this
    # rule judges; a genuine bug belongs to the behavioural rules above, which run for
    # exactly the adapters that reach this branch.
    try:
        ev = await store.merge_event(user_id=u, project_id=p, title="X", chapter_id="ch-1")
        await store.update_event_fields(
            user_id=u, event_id=ev.id, title="Y", summary=None, time_cue=None,
            event_date_iso=None, expected_version=ev.version)
    except NotImplementedError as exc:
        pytest.fail(
            f"{_which(store)} is NOT in _EVENT_WRITE_REFUSERS but still refuses the event "
            f"writes ({exc}) — five behavioural rules above are passing vacuously. Either "
            f"implement it or put the adapter back in the set, where the skips are visible."
        )


# ── the paginated browse (T17 A3) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_total_counts_EVERYTHING_that_matched_not_just_the_page(store):
    """The rule the whole `(rows, total)` shape exists for.

    A `total` that shrank to the page size would make "showing 1-50 of 50" true on every
    page of a thousand — an off-by-a-page bug that looks correct on the first screen and is
    invisible in a unit test that only ever asks for one page.
    """
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("needs merge_event to create the rows — AGE refuses it")
    u, p, _ = _ids()
    for i in range(5):
        await store.merge_event(
            user_id=u, project_id=p, title=f"Event {i}", chapter_id=f"ch-{i}",
            source_type="chapter", event_order=(i + 1) * 1_000)

    rows, total = await store.events_page(user_id=u, project_id=p, limit=2, offset=0)
    assert len(rows) == 2, f"limit ignored: {len(rows)} rows"
    assert total == 5, f"total reported {total}, but 5 events matched the filters"

    page2, total2 = await store.events_page(user_id=u, project_id=p, limit=2, offset=2)
    assert total2 == 5, "the total changed with the page — it must describe the FILTERS"
    assert {e.id for e in page2}.isdisjoint({e.id for e in rows}), (
        "offset did not advance — page 2 repeats page 1"
    )


@pytest.mark.asyncio
async def test_the_browse_and_the_window_agree_about_which_events_match(store):
    """The browse must not become a second, drifting definition of "matching". If these two
    ever disagree, one of them is wrong and no test that uses only one would say so."""
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("needs merge_event to create the rows — AGE refuses it")
    u, p, _ = _ids()
    for i in range(4):
        await store.merge_event(
            user_id=u, project_id=p, title=f"W{i}", chapter_id=f"ch-{i}",
            source_type="chapter", event_order=(i + 1) * 1_000)

    windowed = await store.events_in_window(
        user_id=u, project_id=p, after=2_000, before=3_000)
    paged, total = await store.events_page(
        user_id=u, project_id=p, after=2_000, before=3_000, limit=100)
    assert {e.id for e in paged} == {e.id for e in windowed}, (
        "the browse and the window disagree about which events are in the range"
    )
    assert total == len(windowed)


# ── facts, and the ordinal chain (T17 A7) ────────────────────────────────────

#: AGE refuses the fact WRITE (D-AGE-FACT-WRITE-UNIMPLEMENTED); the refusal is asserted below.
# T59 (2026-08-22): EMPTY. `D-AGE-FACT-WRITE-UNIMPLEMENTED` said `maintain_chain` needed
# "an ordered window over sibling facts in ONE statement". One STATEMENT was never the
# requirement -- one TRANSACTION was, the same conflation T58 corrected for the event
# writes. Kept as a set for the same reason as its event twin: it is how a future refusal
# stays VISIBLE rather than becoming a silently-passing adapter.
_FACT_WRITE_REFUSERS: set[str] = set()


@pytest.mark.asyncio
async def test_merge_fact_returns_a_CONTENT_KEYED_id(store):
    """⚠️ **This rule CANNOT detect a merge_fact that appends**, and that is worth stating
    rather than leaving as an unexamined green.

    A fact's id is derived from its content in both implementations, so a store that minted a
    second node would return the SAME id and this assertion would still pass. The bite proved
    it: forcing the fake to always create reds nothing. Detecting duplication needs a COUNT,
    and the port has no fact read — see `D-PORT-CANNOT-OBSERVE-FACT-STATE`.

    What it does cover: the id is stable and content-derived, which is what every caller that
    stores a fact id depends on.
    """
    if _which(store) in _FACT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_fact_write")
    u, p, _ = _ids()
    a = await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="wields the frost blade", subject_id="e1",
                               from_order=10_000)
    b = await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="wields the frost blade", subject_id="e1",
                               from_order=10_000)
    assert a.id == b.id
    c = await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="wields a DIFFERENT blade", subject_id="e1",
                               from_order=10_000)
    assert c.id != a.id, "two different contents collapsed into one id"


@pytest.mark.asyncio
async def test_merge_fact_ACCEPTS_maintain_chain_without_raising(store):
    """What this suite can honestly assert about the chain today — and it is not much.

    🔻 `D-PORT-CANNOT-OBSERVE-FACT-STATE`. The chain is the operation's whole point, and
    **no port caller can see it**: `Fact` carries no `subject_id` (the real store attaches the
    subject with an ABOUT edge), the chain is re-derived AFTER the merge so the returned object
    predates it, and the port has no fact READ to re-fetch with. Three earlier versions of this
    rule asserted `first.valid_to_ordinal == 40_000` and failed on BOTH real adapters for that
    reason — the assertion was about a stale object, not about the store.

    So this rule covers only what is observable: the flag is accepted and the write completes.
    That is deliberately weak, and it is stated here rather than dressed up: a fourth version
    asserting `valid_to_ordinal is None` on the same stale object would have PASSED on every
    adapter while proving nothing at all.
    """
    if _which(store) in _FACT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_fact_write")
    u, p, _ = _ids()
    first = await store.merge_fact(user_id=u, project_id=p, type="attribute",
                                   content="an outer disciple", subject_id="e1",
                                   from_order=10_000, maintain_chain=True)
    second = await store.merge_fact(user_id=u, project_id=p, type="attribute",
                                    content="an inner disciple", subject_id="e1",
                                    from_order=40_000, maintain_chain=True)
    assert first.id != second.id, "two different fact contents collapsed into one node"
    assert second.valid_from_ordinal == 40_000


@pytest.mark.asyncio
async def test_the_fact_write_REFUSERS_SET_is_honest_in_BOTH_directions(store):
    """Same shape as its event twin, and rewritten for the same reason (T58/T59).

    `if not in refusers: skip` becomes a permanent skip on EVERY adapter the moment the set
    empties, which is exactly what emptying it did. A test that skips on all four parameters
    still prints as coverage.
    """
    u, p, _ = _ids()
    if _which(store) in _FACT_WRITE_REFUSERS:
        with pytest.raises(NotImplementedError, match="D-AGE-FACT-WRITE-UNIMPLEMENTED"):
            await store.merge_fact(user_id=u, project_id=p, type="attribute", content="x",
                                   subject_id="e1", from_order=1, maintain_chain=True)
        return
    subject = await _a_subject(store, u, p)
    try:
        await store.merge_fact(
            user_id=u, project_id=p, type="attribute", content="x",
            subject_id=subject, from_order=1, maintain_chain=True)
    except NotImplementedError as exc:
        pytest.fail(
            f"{_which(store)} is NOT in _FACT_WRITE_REFUSERS but still refuses the fact "
            f"write ({exc}) — the chain rules are passing vacuously. Either implement it or "
            f"put the adapter back in the set, where the skips are visible."
        )


# ── facts_for: the read that makes the merge checkable (T17 A8 / SPEC §1.1) ───

#: AGE refuses the fact WRITE but IMPLEMENTS the read (rule 9: raise only what you cannot
#: honour). So its arm of these rules seeds with raw Cypher and reads back through the port
#: — otherwise `AgeGraphStore.facts_for` would ship as code no rule can reach.
# T59: EMPTY -- AGE now implements the fact WRITE too, so its read arm no longer has to
# lean on the as_of rules for coverage. The two chain rules below run for `age`.
_FACT_WRITE_REFUSERS_READ_OK: set[str] = set()


async def _a_subject(store, u, p, name="Kai"):
    """A REAL entity, because `merge_fact`'s ABOUT edge is conditional on one existing.

    ⚠️ Measured, not assumed: the older fact rules above pass `subject_id="e1"` — a string
    naming nothing. On Neo4j that MERGEs no `ABOUT` edge at all (the repo doc says *"when
    given AND the entity exists for this user"*), while the fake records the subject in a
    side table regardless. Every rule below would therefore have read an empty list from the
    real adapter and a full one from the fake, and the honest-looking conclusion would have
    been "Neo4j's facts_for is broken."
    """
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name=name, kind="character", source_type="chapter")
    return e.id


async def _seed_age_fact(store, u, p, subject, *, fid, type, content,
                         vfrom=None, vto=None):
    """Seed one `(:Fact)-[:ABOUT]->(:Entity)` directly, for the adapter whose only fact
    write refuses. The READ is what is under test; the seed is scaffolding."""
    vf = "NULL" if vfrom is None else str(vfrom)
    vt = "NULL" if vto is None else str(vto)
    await store._run(
        f"MATCH (e:Entity {{id: '{subject}', user_id: '{u}'}}) "
        f"MERGE (f:Fact {{id: '{fid}'}}) "
        f"SET f.user_id = '{u}', f.project_id = '{p}', f.type = '{type}', "
        f"    f.content = '{content}', f.canonical_content = '{content}', "
        f"    f.confidence = 0.9, f.valid_from_ordinal = {vf}, f.valid_to_ordinal = {vt} "
        f"MERGE (f)-[:ABOUT]->(e) RETURN f")


@pytest.mark.asyncio
async def test_facts_for_sees_the_ORDINAL_CHAIN_that_merge_fact_maintained(store):
    """🔴 **The rule `merge_fact` could not have.** `test_merge_fact_ACCEPTS_maintain_chain…`
    above says outright that it proves only that the flag does not raise — the chain is
    re-derived AFTER the merge, so the returned `Fact` predates it and carries no
    `subject_id` to re-find its family with. Three earlier versions asserted on that stale
    object and failed on both real adapters for that reason.

    Reading the family back closes it: the earlier fact must be CLOSED at the later one's
    ordinal, and the later one must be OPEN. An adapter that accepted the flag and closed
    nothing leaves every fact open forever — every as-of read then answers with the latest
    value at every position, which is a book with no history reported as a working timeline.
    """
    if _which(store) in _FACT_WRITE_REFUSERS_READ_OK:
        pytest.skip("AGE refuses the fact write — its read arm is covered by the as_of rules")
    u, p, _ = _ids()
    subject = await _a_subject(store, u, p)
    await store.merge_fact(user_id=u, project_id=p, type="attribute",
                           content="an outer disciple", subject_id=subject,
                           from_order=10_000, maintain_chain=True)
    await store.merge_fact(user_id=u, project_id=p, type="attribute",
                           content="an inner disciple", subject_id=subject,
                           from_order=40_000, maintain_chain=True)

    chain = await store.facts_for(user_id=u, subject_id=subject, type="attribute")
    assert [f.valid_from_ordinal for f in chain] == [10_000, 40_000], (
        "the family did not come back oldest-first on the story axis")
    assert chain[0].valid_to_ordinal == 40_000, (
        "the earlier fact was left OPEN — maintain_chain closed no interval")
    assert chain[1].valid_to_ordinal is None, "the newest fact must stay open"


@pytest.mark.asyncio
async def test_facts_for_COUNTS_so_a_re_merge_cannot_hide_a_duplicate(store):
    """🔴 **The other rule the port could not express.** `merge_fact`'s id is derived from
    its content, so an appending store returns the SAME id a merging one does — the bite on
    that rule confirmed it: forcing the fake to always create reds nothing. Duplication is
    only visible as a COUNT over the family, which needs a read.
    """
    if _which(store) in _FACT_WRITE_REFUSERS_READ_OK:
        pytest.skip("AGE refuses the fact write — its read arm is covered by the as_of rules")
    u, p, _ = _ids()
    subject = await _a_subject(store, u, p)
    for _ in range(3):
        await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="wields the frost blade", subject_id=subject,
                               from_order=10_000)
    facts = await store.facts_for(user_id=u, subject_id=subject, type="attribute")
    assert len(facts) == 1, (
        f"three merges of one content produced {len(facts)} facts — the store APPENDS")


@pytest.mark.asyncio
async def test_facts_for_as_of_is_HALF_OPEN_at_the_boundary_chapter(store):
    """`valid_from <= N < valid_to` — the LOCKED convention (§12.3.1), checked at the exact
    ordinal where an off-by-one lives. At N = the close, the superseded fact is GONE and its
    successor has taken over; one chapter earlier it is still the answer. Both directions,
    because a read that returned everything would pass the first assertion alone.
    """
    u, p, _ = _ids()
    subject = await _a_subject(store, u, p)
    if _which(store) in _FACT_WRITE_REFUSERS_READ_OK:
        await _seed_age_fact(store, u, p, subject, fid=f"f-old-{subject}",
                             type="attribute", content="an outer disciple",
                             vfrom=10_000, vto=40_000)
        await _seed_age_fact(store, u, p, subject, fid=f"f-new-{subject}",
                             type="attribute", content="an inner disciple",
                             vfrom=40_000, vto=None)
    else:
        await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="an outer disciple", subject_id=subject,
                               from_order=10_000, maintain_chain=True)
        await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="an inner disciple", subject_id=subject,
                               from_order=40_000, maintain_chain=True)

    before = await store.facts_for(user_id=u, subject_id=subject, type="attribute",
                                   as_of=39_999)
    assert [f.content for f in before] == ["an outer disciple"], (
        "one ordinal BEFORE the close, the superseded fact must still be the answer")
    at = await store.facts_for(user_id=u, subject_id=subject, type="attribute",
                               as_of=40_000)
    assert [f.content for f in at] == ["an inner disciple"], (
        "AT the close the interval is already shut — half-open, not inclusive")


@pytest.mark.asyncio
async def test_facts_for_EXCLUDES_a_positionless_fact_from_a_TIMED_read(store):
    """The same rule `relations_for` states, on the other node type: a fact with no ordinal
    cannot be placed on the axis, so a timed read must not return it — while a HEAD read
    must, or the chat-tool and legacy facts silently vanish from the codex.

    Both halves are asserted. A read that dropped positionless facts everywhere would pass
    the exclusion on its own, and that is the more damaging of the two failures.
    """
    u, p, _ = _ids()
    subject = await _a_subject(store, u, p)
    if _which(store) in _FACT_WRITE_REFUSERS_READ_OK:
        await _seed_age_fact(store, u, p, subject, fid=f"f-pos-{subject}",
                             type="attribute", content="positioned", vfrom=10_000)
        await _seed_age_fact(store, u, p, subject, fid=f"f-null-{subject}",
                             type="attribute", content="positionless", vfrom=None)
    else:
        await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="positioned", subject_id=subject, from_order=10_000)
        await store.merge_fact(user_id=u, project_id=p, type="attribute",
                               content="positionless", subject_id=subject)

    head = {f.content for f in
            await store.facts_for(user_id=u, subject_id=subject, type="attribute")}
    assert head == {"positioned", "positionless"}, (
        "a HEAD read must carry the untimed fact — dropping it hides every chat-tool fact")
    timed = {f.content for f in
             await store.facts_for(user_id=u, subject_id=subject, type="attribute",
                                   as_of=10_000)}
    assert timed == {"positioned"}, (
        "a positionless fact leaked into a timed read — untimed data in a timed answer")


# ── the project as a whole (T17 A10, spec §1.2) ──────────────────────────────

@pytest.mark.asyncio
async def test_project_graph_stats_counts_EACH_LABEL_SEPARATELY(store):
    """🔴 The one bug worth catching here, and the reason the fixture is lopsided.

    The unit test this replaces handed the reconciler a mocked session that answered `10` to
    every query and asserted all three columns were `10` — green for a store that wrote the
    entity count into all three, and green for one that ignored the label entirely. So the
    counts here are DISTINCT by construction: 2 entities, 3 facts, 1 event. Equal fixtures
    make a label mix-up invisible, which is the same green-by-construction shape the plan has
    now hit in a detector, a gate and a bite.
    """
    u, p, _ = _ids()
    for name in ("Kai", "Mira"):
        await store.resolve_or_merge_entity(
            user_id=u, project_id=p, name=name, kind="character", source_type="chapter")

    subject = await _a_subject(store, u, p, name="Kai")
    if _which(store) in _FACT_WRITE_REFUSERS_READ_OK:
        for i in range(3):
            await _seed_age_fact(store, u, p, subject, fid=f"f-stat-{i}-{subject}",
                                 type="attribute", content=f"fact {i}")
    else:
        for i in range(3):
            await store.merge_fact(user_id=u, project_id=p, type="attribute",
                                   content=f"fact {i}", subject_id=subject)

    expect_events = 0
    if _which(store) not in _EVENT_WRITE_REFUSERS:
        await _an_event(store, u, p, title="The Duel")
        expect_events = 1

    stats = await store.project_graph_stats(user_id=u, project_id=p)
    assert stats["entity_count"] == 2, f"entity_count is wrong: {stats}"
    assert stats["fact_count"] == 3, f"fact_count is wrong: {stats}"
    assert stats["event_count"] == expect_events, f"event_count is wrong: {stats}"


@pytest.mark.asyncio
async def test_project_graph_stats_counts_ONLY_this_tenant_and_this_project(store):
    """A stats card that counted the neighbouring book reads as a working recount and is
    wrong on every dashboard tile — silent, which is why it is a conformance rule and not a
    docstring. Both axes are checked: another USER's node and another PROJECT of the SAME
    user, because a store that scoped by user alone would pass the first half."""
    u, p, other_user = _ids()
    _, other_project, _ = _ids()

    await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    await store.resolve_or_merge_entity(
        user_id=u, project_id=other_project, name="Mira", kind="character",
        source_type="chapter")
    await store.resolve_or_merge_entity(
        user_id=other_user, project_id=p, name="Nell", kind="character",
        source_type="chapter")

    assert (await store.project_graph_stats(user_id=u, project_id=p))["entity_count"] == 1


@pytest.mark.asyncio
async def test_an_EMPTY_project_answers_zeros_rather_than_an_empty_dict(store):
    """An empty graph is a legitimate state — extraction enabled, nothing run yet — and the
    caller renders "Ready" from it. A store returning `{}` makes every consumer do
    `stats.get(k, 0)`, and the day one adapter starts omitting a key that lookup turns a
    missing count into a real zero. Every key in `COUNTABLE_LABELS` is present, always.

    ⚠️ **`passage_count` must be ABSENT**, and this is where that shape is pinned. The repo
    function behind the Neo4j adapter counts four labels; a passage is the VECTOR layer's
    row, §3.1 moves it to Postgres, and neither AGE nor Kuzu has a passage table at all. An
    adapter that leaked the fourth key would be answering for a store it does not hold — and
    the two honest answers available to it are a lie (`0`) or a refusal that makes a stats
    card unrenderable.
    """
    u, p, _ = _ids()
    stats = await store.project_graph_stats(user_id=u, project_id=p)
    assert stats == {"entity_count": 0, "fact_count": 0, "event_count": 0}, (
        f"an empty project must answer every count at zero and nothing else: {stats}")


@pytest.mark.asyncio
async def test_an_ARCHIVED_entity_still_COUNTS(store):
    """The one place `find_entities_by_name`'s default-hide rule must NOT apply. The Cypher
    behind this is a bare label match with a tenant filter and no archive predicate, so an
    adapter that reused the resolver's visibility rule would disagree with the engine it is
    replacing — and the disagreement would only ever show up as a dashboard tile drifting
    down after an author archives something. A stats card counts what is in the graph."""
    u, p, _ = _ids()
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    await store.archive_entity(user_id=u, canonical_id=e.id, reason="merged away")
    assert await store.find_entities_by_name(user_id=u, project_id=p, name="Kai") == [], (
        "precondition: the archive did not take, so this rule proves nothing")
    stats = await store.project_graph_stats(user_id=u, project_id=p)
    assert stats["entity_count"] == 1, (
        "an archived entity vanished from the stats card — the resolver's visibility rule "
        f"leaked into a raw count: {stats}")


@pytest.mark.asyncio
async def test_a_re_mention_does_not_MOVE_a_facts_story_birth(store):
    """🔴 **The seventh real Kuzu bug, and conformance had no rule for it.** T43's differential
    found it: Neo4j coalesces `valid_from_ordinal` on MATCH (*"never overwrite an existing
    one"* — `facts.py`), Kuzu assigned it, so re-mentioning the same content in a later
    chapter moved the fact's birth forward.

    The consequence is silent and directional. `merge_fact` is CONTENT-keyed, so the second
    call lands on the same node; an as-of read at the ORIGINAL chapter then stops returning a
    fact that was already established there — established canon disappearing from a reader's
    past, while the codex at HEAD looks perfect. It is the same failure
    `test_merge_event_is_idempotent_and_keeps_the_EARLIEST_reading_position` pins for events,
    on the other node type, and it went unpinned for both real adapters.

    ⚠️ The LATER mention must come SECOND. Mentioning 40 000 first cannot discriminate —
    backfill-wins and overwrite-wins both end at 12 000, which is the vacuity that made the
    event rule's first cut green under its own mutation.
    """
    if _which(store) in _FACT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_fact_write")
    u, p, _ = _ids()
    subject = await _a_subject(store, u, p)
    first = await store.merge_fact(
        user_id=u, project_id=p, type="attribute", content="an outer disciple",
        subject_id=subject, valid_from_ordinal=12_000)
    again = await store.merge_fact(
        user_id=u, project_id=p, type="attribute", content="an outer disciple",
        subject_id=subject, valid_from_ordinal=40_000)
    assert again.id == first.id, "content-keyed merge minted a SECOND fact for one content"
    assert again.valid_from_ordinal == 12_000, (
        "a re-mention moved the fact's story birth forward — an as-of read at chapter 12 "
        f"now misses canon it already established (got {again.valid_from_ordinal})")

    # And the read agrees, because the field on a returned object is not what a caller sees.
    at_first = await store.facts_for(user_id=u, subject_id=subject, type="attribute",
                                     as_of=12_000)
    assert [f.content for f in at_first] == ["an outer disciple"], (
        "the fact vanished from an as-of read at the chapter that established it")


@pytest.mark.asyncio
async def test_a_POSITIONLESS_fact_is_BACKFILLED_by_a_later_positioned_mention(store):
    """The other half of the same coalesce, and the half that makes it a backfill rather than
    a freeze. A fact first seen through a positionless source (a chat tool, legacy data) has
    NULL — and the next positioned mention must FILL it, or the fact stays invisible to every
    timed read forever. An adapter that hardened the first rule into "never write it" passes
    the rule above and fails every author here."""
    if _which(store) in _FACT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_fact_write")
    u, p, _ = _ids()
    subject = await _a_subject(store, u, p)
    await store.merge_fact(user_id=u, project_id=p, type="attribute",
                           content="a sworn blade", subject_id=subject)
    filled = await store.merge_fact(user_id=u, project_id=p, type="attribute",
                                    content="a sworn blade", subject_id=subject,
                                    valid_from_ordinal=12_000)
    assert filled.valid_from_ordinal == 12_000, (
        "a positioned re-mention did not backfill the story position — the fact stays "
        "invisible to every timed read")


@pytest.mark.asyncio
async def test_an_AUTHOR_RENAME_does_not_fork_the_event_on_re_extraction(store):
    """🔴 **T35d — the identity rule for events, and the differential's `merge_event`
    divergence is this rule missing.**

    An event's title comes from the PROSE: `pass2_writer` passes the extractor's `name_clean`,
    which is read out of the chapter. So when an author renames an event in the studio,
    re-extracting that chapter still produces the **original** title — and must land on the
    same node. `neo4j_repos/events.py` says so in as many words, as a deliberate design:

        "the node id (a hash of the original title) is IMMUTABLE — a title edit updates the
         display title + canonical_title but the id is stable, so a future extraction with the
         OLD title still dedupes onto this node (rename has no downstream consequence beyond
         display)."

    An adapter that keys on the CURRENT canonical title inverts that: every re-extraction after
    any author rename mints a duplicate event. Silent, cumulative, and it grows with exactly the
    thing an engaged author does most — tidying titles.

    ⚠️ The re-mention must use the ORIGINAL title, because that is what the extractor produces.
    Re-mentioning with the NEW title cannot discriminate: both designs match it.
    """
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_event_writes")
    u, p, _ = _ids()
    first = await _an_event(store, u, p, title="Kai duels Zhao", event_order=12_000)
    renamed = await store.update_event_fields(
        user_id=u, event_id=first.id, title="The Duel at Dawn", summary=None,
        time_cue=None, event_date_iso=None, expected_version=first.version)
    assert renamed is not None, "precondition: the rename did not apply"

    again = await _an_event(store, u, p, title="Kai duels Zhao", event_order=12_000)
    assert again.id == first.id, (
        "re-extracting the chapter after an author rename FORKED the event — the adapter keys "
        "identity on the mutable title, so every later pass mints another duplicate")

    page, total = await store.events_page(user_id=u, project_id=p, limit=50)
    mine = [e for e in page if e.id == first.id]
    assert len(mine) == 1 and total == 1, (
        f"one authored event, {total} nodes in the browse — the fork is visible to the reader")


@pytest.mark.asyncio
async def test_the_rename_still_CHANGES_what_the_reader_sees(store):
    """The other half, and the one an over-eager "make identity stable" fix breaks: the author's
    new title must actually win on read. An adapter that pinned the title to keep the id stable
    would pass the rule above and silently discard every rename."""
    if _which(store) in _EVENT_WRITE_REFUSERS:
        pytest.skip("AGE refuses this write — see test_age_REFUSES_the_event_writes")
    u, p, _ = _ids()
    ev = await _an_event(store, u, p, title="Kai duels Zhao", event_order=12_000)
    await store.update_event_fields(
        user_id=u, event_id=ev.id, title="The Duel at Dawn", summary=None,
        time_cue=None, event_date_iso=None, expected_version=ev.version)
    after = await _an_event(store, u, p, title="Kai duels Zhao", event_order=12_000)
    assert after.title == "The Duel at Dawn", (
        f"the author's rename was overwritten by a re-extraction: {after.title!r}")


# ── neighborhood + status_at_order ───────────────────────────────────────────
#
# T89. These two were the ONLY port methods with no rule here, and a live run on the AGE
# backend found `neighborhood` returning HTTP 500 from `/internal/knowledge/wiki-neighborhood`
# on the first call it ever received:
#
#     ValidationError: 1 validation error for EntityDetail
#     entity  Field required [input_value={'id': 'b0a88a54...', 'relations': []}]
#
# The adapter spread the entity across the top level instead of nesting it. Nineteen of
# twenty-one port methods were conformed against four adapters; the twentieth had never been
# called by any test, against any adapter, and shipped unable to return at all.
#
# Writing the missing rules then found two MORE defects behind the crash, and neither was in
# the module the crash pointed at — see each rule.


async def _anchored(store, u, p, gid, name="Kai"):
    """An entity reachable by `glossary_entity_id`.

    The hook exists because the port can READ by `glossary_entity_id` and has no method that
    WRITES one — which is the structural reason nobody wrote these rules. It follows the
    `_mk_source` precedent rather than inventing a second escape-hatch style.
    """
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name=name, kind="character", source_type="chapter")
    await store._set_glossary(u, e.id, gid)               # type: ignore[attr-defined]
    return e


@pytest.mark.asyncio
async def test_neighborhood_nests_the_entity_and_scopes_to_the_owner(store):
    """The shape is the contract: `EntityDetail.entity` is a nested `Entity`, not the entity's
    fields spread across the top level. An adapter that flattens does not return a wrong
    answer — it raises, on every call, which is how this reached a live 500."""
    u, p, other = _ids()
    gid = f"gl-{uuid.uuid4().hex[:12]}"
    e = await _anchored(store, u, p, gid)

    detail = await store.neighborhood(user_id=u, glossary_entity_id=gid)
    assert detail is not None, "the anchored entity was not found by its glossary id"
    assert detail.entity.id == e.id, "the entity is not nested under `.entity`"

    assert await store.neighborhood(user_id=other, glossary_entity_id=gid) is None, (
        "another user read this neighbourhood — the glossary id is not owner-scoped")
    assert await store.neighborhood(
        user_id=u, glossary_entity_id=f"gl-{uuid.uuid4().hex[:12]}") is None


@pytest.mark.asyncio
async def test_neighborhood_REPORTS_the_cap_it_applied(store):
    """`total_relations` is the UNCAPPED count and `relations_truncated` is derived from it.

    ⚠️ Found in TWO independent adapters at once — AGE and the Fake both capped the list and
    left `total_relations` at its `0` default, so every caller was told "nothing was cut"
    on exactly the hub entities where something was. The Fake's own comment read *"The cap is
    applied, not ignored"* directly above the line that failed to report it. Neither could be
    caught by a rule that only counts `len(relations)` — the cap itself worked."""
    u, p, _ = _ids()
    gid = f"gl-{uuid.uuid4().hex[:12]}"
    anchor = await _anchored(store, u, p, gid)
    for i in range(4):
        peer = await store.resolve_or_merge_entity(
            user_id=u, project_id=p, name=f"Peer{i}", kind="character", source_type="chapter")
        await store.upsert_relation(
            user_id=u, subject_id=anchor.id, object_id=peer.id,
            predicate="ally_of", confidence=0.9)

    full = await store.neighborhood(user_id=u, glossary_entity_id=gid, rel_cap=50)
    assert full.total_relations == 4, f"uncapped total is wrong: {full.total_relations}"
    assert full.relations_truncated is False, "reported truncated when nothing was cut"

    cut = await store.neighborhood(user_id=u, glossary_entity_id=gid, rel_cap=2)
    assert len(cut.relations) == 2, "the cap was not applied"
    assert cut.total_relations == 4, (
        f"the cap overwrote the total: total_relations={cut.total_relations}, so the caller "
        "cannot tell a 2-edge entity from a truncated 4-edge one")
    assert cut.relations_truncated is True, (
        "two of four edges were dropped and the answer says it is complete")


@pytest.mark.asyncio
async def test_neighborhood_does_NOT_apply_a_confidence_floor(store):
    """A neighbourhood filters on `valid_until IS NULL` and nothing else.

    ⚠️ The AGE adapter delegated to `relations_for`, whose DEFAULTS are `min_confidence=0.8`
    plus an archived-peer exclusion. Both read plausibly — they are the right filters for
    "this entity's relations" — and neither belongs to this query. The effect was a silent
    under-report on one backend only: a low-confidence edge simply was not in the context
    block, with no error anywhere. This rule fails on the delegating shape and passes on the
    dedicated one, which is the only difference between them."""
    u, p, _ = _ids()
    gid = f"gl-{uuid.uuid4().hex[:12]}"
    anchor = await _anchored(store, u, p, gid)
    weak = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Rumoured", kind="character", source_type="chapter")
    await store.upsert_relation(
        user_id=u, subject_id=anchor.id, object_id=weak.id,
        predicate="rumoured_ally_of", confidence=0.3)

    detail = await store.neighborhood(user_id=u, glossary_entity_id=gid)
    assert [r.predicate for r in detail.relations] == ["rumoured_ally_of"], (
        f"a confidence-0.3 edge was dropped from the neighbourhood: {detail.relations}")
    assert detail.total_relations == 1


@pytest.mark.asyncio
async def test_status_at_order_fails_OPEN_to_active(store):
    """An entity with no qualifying transition is `active`, and the asymmetry is the point:
    a wrongly-`gone` entity vanishes from a panel, a wrongly-`active` one silently un-kills a
    character. Neo4j spells this `coalesce(latest.status, 'active')`; every adapter must
    agree, including for an entity id that does not exist at all."""
    u, p, _ = _ids()
    e = await store.resolve_or_merge_entity(
        user_id=u, project_id=p, name="Kai", kind="character", source_type="chapter")
    ghost = f"e-{uuid.uuid4().hex[:12]}"

    got = await store.status_at_order(
        user_id=u, project_id=p, entity_ids=[e.id, ghost], at_order=10_000)
    assert got == {e.id: "active", ghost: "active"}, (
        f"an entity with no transition was not reported active: {got}")

    assert await store.status_at_order(
        user_id=u, project_id=p, entity_ids=[], at_order=10_000) == {}
