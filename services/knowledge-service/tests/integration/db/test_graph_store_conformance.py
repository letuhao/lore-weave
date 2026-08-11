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


@pytest_asyncio.fixture(params=["fake", "neo4j"])
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
        yield FakeGraphStore()
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
            yield Neo4jGraphStore(session)
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
