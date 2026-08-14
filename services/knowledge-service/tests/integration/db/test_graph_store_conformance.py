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

            async def _mk_kuzu_source(_u, _sid):
                return None

            kz._mk_source = _mk_kuzu_source            # type: ignore[attr-defined]
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
_EVENT_WRITE_REFUSERS = {"age"}


#: The rules `KuzuGraphStore` is CONFORMED ON today. It implements the entity surface and
#: refuses the rest (T42, rule 9), so it is judged on exactly these and skipped elsewhere —
#: named individually rather than gated by a blanket "kuzu is partial", because a blanket skip
#: grows silently: an operation implemented later would stay unjudged and nothing would say so.
#: Adding a method means adding its rules HERE, in the same commit.
_KUZU_CONFORMED = {
    "test_resolving_the_same_name_twice_returns_the_same_entity",
    "test_the_same_name_in_two_projects_is_two_entities",
    "test_another_users_entity_is_not_found_by_name",
    "test_an_archived_entity_is_excluded_from_name_resolution_by_default",
    "test_archiving_another_users_entity_is_a_miss_not_a_write",
    "test_restore_undoes_an_archive",
    # relations, added WITH the methods (T42-kuzu-4) rather than after — see the note above:
    # a scope list that lags the implementation leaves rules unjudged and says nothing.
    "test_as_of_respects_the_interval_start",
    "test_a_positionless_edge_is_excluded_by_a_timed_read_but_not_by_a_head_read",
    "test_low_confidence_edges_are_filtered_by_default",
    "test_an_edge_to_an_ARCHIVED_peer_is_excluded",
    "test_another_users_relations_are_not_returned",
    "test_get_relation_finds_it_and_is_a_MISS_for_another_user",
    "test_invalidate_hides_the_edge_from_ordinary_reads_and_is_idempotent",
    "test_recreate_RESURRECTS_an_invalidated_edge_rather_than_duplicating_it",
    "test_an_authored_relation_carries_its_story_position",
    # events (T42-kuzu-5), added WITH the methods
    "test_merge_event_is_idempotent_and_keeps_the_EARLIEST_reading_position",
    "test_get_event_is_a_MISS_for_another_user",
    "test_archive_event_is_idempotent",
    "test_the_browse_and_the_window_agree_about_which_events_match",
    # facts (T42-kuzu-7). Kuzu HONOURS maintain_chain where AGE refused it -- see the method.
    "test_merge_fact_returns_a_CONTENT_KEYED_id",
    "test_merge_fact_ACCEPTS_maintain_chain_without_raising",
    "test_facts_for_sees_the_ORDINAL_CHAIN_that_merge_fact_maintained",
    "test_facts_for_COUNTS_so_a_re_merge_cannot_hide_a_duplicate",
    "test_facts_for_as_of_is_HALF_OPEN_at_the_boundary_chapter",
    "test_facts_for_EXCLUDES_a_positionless_fact_from_a_TIMED_read",
}


@pytest.fixture(autouse=True)
def _kuzu_scope(request):
    """Skip the rules Kuzu does not yet implement — and ONLY those.

    ⚠️ The skip is the danger this file already warns about, so it is paired with
    `test_kuzu_REFUSES_what_the_scope_list_skips` below: every unimplemented operation must
    actually raise. Without that, "Kuzu is skipped here" silently becomes "Kuzu passed",
    which is the exact failure mode `_EVENT_WRITE_REFUSERS` exists to prevent for AGE.
    """
    if "store" not in request.fixturenames:
        return
    if request.node.callspec.params.get("store") != "kuzu":
        return
    name = request.node.originalname or request.node.name
    if name not in _KUZU_CONFORMED:
        pytest.skip(f"KuzuGraphStore implements the entity surface only — {name} needs an "
                    "operation it refuses (T42; see test_kuzu_REFUSES_what_the_scope_list_skips)")


@pytest.mark.asyncio
async def test_kuzu_REFUSES_what_the_scope_list_skips():
    """The other half of `_KUZU_CONFORMED`. A scope list is a claim about what is unbuilt; this
    is the check that the claim is true, so a skipped rule can never be mistaken for a passing
    one. Runs without the `store` fixture on purpose — it needs no database."""
    pytest.importorskip("kuzu", reason="kuzu is an optional T43-candidate dependency")
    from app.adapters.kuzu_graph_store import KuzuGraphStore

    store = KuzuGraphStore(conn=None)
    for op in ("update_event_fields", "add_evidence", "status_at_order"):
        with pytest.raises(NotImplementedError, match="T42"):
            await getattr(store, op)()


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
async def test_age_REFUSES_the_event_writes_rather_than_answering_wrongly(store):
    """The skips above are only honest while the refusal is REAL.

    Without this, `_EVENT_WRITE_REFUSERS` would be a way to make AGE's gap invisible — the
    suite would report green for three adapters while one silently did nothing. The port's
    rule is that an operation which answers wrongly is worse than one that refuses, and an
    empty return here would read as "no such event" to every caller.
    """
    if _which(store) not in _EVENT_WRITE_REFUSERS:
        pytest.skip("only the refusing adapters are pinned here")
    u, p, _ = _ids()
    with pytest.raises(NotImplementedError, match="D-AGE-EVENT-WRITE-UNIMPLEMENTED"):
        await store.merge_event(user_id=u, project_id=p, title="X", chapter_id="ch-1")
    with pytest.raises(NotImplementedError, match="D-AGE-EVENT-WRITE-UNIMPLEMENTED"):
        await store.update_event_fields(
            user_id=u, event_id="x", title=None, summary=None, time_cue=None,
            event_date_iso=None, expected_version=1)


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
_FACT_WRITE_REFUSERS = {"age"}


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
async def test_age_REFUSES_the_fact_write_rather_than_answering_wrongly(store):
    if _which(store) not in _FACT_WRITE_REFUSERS:
        pytest.skip("only the refusing adapters are pinned here")
    u, p, _ = _ids()
    with pytest.raises(NotImplementedError, match="D-AGE-FACT-WRITE-UNIMPLEMENTED"):
        await store.merge_fact(user_id=u, project_id=p, type="attribute", content="x",
                               subject_id="e1", from_order=1, maintain_chain=True)


# ── facts_for: the read that makes the merge checkable (T17 A8 / SPEC §1.1) ───

#: AGE refuses the fact WRITE but IMPLEMENTS the read (rule 9: raise only what you cannot
#: honour). So its arm of these rules seeds with raw Cypher and reads back through the port
#: — otherwise `AgeGraphStore.facts_for` would ship as code no rule can reach.
_FACT_WRITE_REFUSERS_READ_OK = {"age"}


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
