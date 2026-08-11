"""T43 — Neo4j vs AGE, shadowed on real traffic, with the coverage floor enforced.

This is the measurement decision **X1** insisted on: *"build BOTH candidates and let the
shadow comparison choose"*, rather than settling the engine by argument. It became runnable
only after T17 put real traffic through the port — before that every operation sat at zero
observations and the floor was unreachable rather than merely unmet.

WHAT EACH TEST IS FOR
---------------------
* the differential run — do the two engines answer the same question the same way?
* the coverage floor — is any operation at ZERO comparisons? That blocks cutover no matter
  how well the others agree.
* the three-outcome rule — `uncovered` must never be counted as agreement, or
  `D-T42-AGE-EVENT-SURFACE` (two AGE methods raise by design) would read as parity.

    docker run -d --name lw-neo4j-scratch -p 7999:7687 \
      -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community
    docker run -d --name lw-age-t43 -e POSTGRES_PASSWORD=x -p 7893:5432 \
      loreweave/postgres-knowledge:18
    TEST_NEO4J_URI=bolt://localhost:7999 \
      TEST_AGE_DSN=postgresql://postgres:x@localhost:7893/postgres \
      pytest tests/integration/db/test_shadow_comparison.py
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from app.adapters.age_graph_store import AgeGraphStore
from app.adapters.neo4j_graph_store import Neo4jGraphStore
from app.adapters.shadow_graph_store import OPERATIONS, ShadowGraphStore
from app.db.age_bootstrap import create_age_pool, ensure_graph

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def shadow(neo4j_driver):
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set — the shadow needs BOTH engines")
    pool = await create_age_pool(dsn, min_size=2, max_size=4)
    try:
        async with pool.acquire() as conn:
            gname = await ensure_graph(conn, uuid.uuid4())
        async with neo4j_driver.session() as session:
            yield ShadowGraphStore(Neo4jGraphStore(session), AgeGraphStore(pool, gname))
    finally:
        await pool.close()


async def _traffic(store, user_id: str, project_id: str) -> None:
    """Exercise every port operation the adapters implement, in a realistic order."""
    a = await store.resolve_or_merge_entity(
        user_id=user_id, project_id=project_id, name="Kai", kind="character",
        source_type="chapter")
    b = await store.resolve_or_merge_entity(
        user_id=user_id, project_id=project_id, name="Mira", kind="character",
        source_type="chapter")
    await store.find_entities_by_name(user_id=user_id, project_id=project_id, name="Kai")
    await store.upsert_relation(
        user_id=user_id, subject_id=a.id, object_id=b.id, predicate="ally_of",
        confidence=0.95, valid_from_ordinal=10)
    await store.relations_for(user_id=user_id, entity_id=a.id, project_id=project_id)
    await store.relations_for(user_id=user_id, entity_id=a.id, project_id=project_id, as_of=12)
    await store.neighborhood(
        user_id=user_id, glossary_entity_id="none-such", project_id=project_id)
    await store.archive_entity(user_id=user_id, canonical_id=a.id, reason="t43")
    await store.restore_entity(user_id=user_id, canonical_id=a.id)
    # The two AGE raises — driven deliberately, so they are RECORDED as uncovered rather
    # than left absent. An operation nobody called and an operation that cannot answer look
    # identical in a report that only counts successes.
    await store.status_at_order(
        user_id=user_id, project_id=project_id, entity_ids=[a.id], at_order=10)
    await store.events_in_window(user_id=user_id, project_id=project_id)


# ── what the FIRST run found, and it is a harness fact, not an engine fact ──────────────
#
# `archive_entity` / `restore_entity` / `upsert_relation` are keyed on a NODE ID. Each engine
# mints its own, so the shadow hands the PRIMARY's id to a secondary that has never seen it:
# Neo4j archives the entity and returns it, AGE matches nothing and returns None. That reads
# as a divergence and is not one — the two stores were asked about different nodes.
#
# Recorded as `D-T43-ID-KEYED-OPS-NEED-A-MAPPING`. Calling it an engine difference would have
# been the worst outcome available: a harness defect published as evidence about AGE, in the
# document that decides the engine.
# The first run named three; the second named a fourth, and the fourth is the one that makes
# the finding structural. `relations_for` takes an `entity_id`, so AGE was asked for the edges
# of a node it does not have — and because `upsert_relation` had already failed for the same
# reason, AGE had no edge to return either way. **Most of this port is id-keyed**, so the
# comparable surface is only what is keyed on NATURAL identity: `resolve_or_merge_entity`
# (name+kind), `find_entities_by_name` (name), `neighborhood` (the glossary anchor, which IS
# shared across engines because glossary-service mints it).
_ID_KEYED = {"archive_entity", "restore_entity", "upsert_relation", "relations_for"}
#: AGE raises here by design — `D-T42-AGE-EVENT-SURFACE`.
_UNIMPLEMENTED = {"status_at_order", "events_in_window"}


async def test_the_two_engines_agree_on_every_comparable_operation(shadow):
    """The differential run, over the operations that CAN be compared.

    A divergence outside `_ID_KEYED` is a real finding about the engines and fails here with
    its samples attached.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    await _traffic(shadow, user_id, project_id)
    report = shadow.coverage_report()

    diverged = {
        op: r for op, r in report["operations"].items()
        if r["diverged"] and op not in _ID_KEYED
    }
    assert not diverged, (
        f"Neo4j and AGE disagreed on {sorted(diverged)} — samples: {report['samples']}"
    )
    # Non-vacuity: if nothing was compared, "no divergence" is not a result.
    compared = [op for op in OPERATIONS if report["operations"][op]["observations"]]
    assert compared, "no operation was compared at all — the run proved nothing"


async def test_the_coverage_floor_names_every_unobserved_operation(shadow):
    """*"No cutover while any port operation has zero shadow observations."*

    The floor is about ABSENCE, and absence is what a success-counting report hides: a run
    that agreed perfectly on `relations_for` and never touched `restore_entity` would be
    evidence about one operation wearing the costume of evidence about the port.

    Two DIFFERENT reasons an operation is unobservable today, and the floor does not care
    which — both block cutover:
      * `_UNIMPLEMENTED` — AGE raises (`D-T42-AGE-EVENT-SURFACE`)
      * `upsert_relation` — id-keyed, so the secondary is asked about a node it lacks
        (`D-T43-ID-KEYED-OPS-NEED-A-MAPPING`)
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    await _traffic(shadow, user_id, project_id)
    report = shadow.coverage_report()

    assert set(report["blocked_by"]) == _UNIMPLEMENTED | {"upsert_relation"}, (
        f"unexpected coverage floor: {report['blocked_by']}"
    )
    assert report["cutover_permitted"] is False, (
        "a cutover was permitted while operations have zero comparisons"
    )
    for op in OPERATIONS:
        if op not in report["blocked_by"]:
            assert report["operations"][op]["observations"] > 0


async def test_an_unimplemented_secondary_is_uncovered_not_agreed(shadow):
    """The three-outcome rule, and the reason it is three.

    `AgeGraphStore.status_at_order` raises `NotImplementedError` by design. If the shadow
    folded that into `agreed`, a method the secondary CANNOT ANSWER would count toward
    parity — a coverage gap reading as a data result, which is the confusion the adapter
    raises to prevent in the first place.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    await shadow.status_at_order(
        user_id=user_id, project_id=project_id, entity_ids=["x"], at_order=1)

    assert shadow.stats.uncovered.get("status_at_order") == 1
    assert shadow.stats.agreed.get("status_at_order", 0) == 0
    assert shadow.stats.diverged.get("status_at_order", 0) == 0
    assert shadow.stats.observations("status_at_order") == 0, (
        "an uncovered call counted as an observation — it would satisfy the coverage floor "
        "without any comparison having happened"
    )


async def test_the_caller_gets_the_primary_answer_even_when_the_secondary_dies(shadow):
    """A shadow that can break the caller converts a measurement into an outage — and the
    first response to an outage is to switch the shadow off, which is how the measurement
    never gets taken."""
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"

    class Exploding:
        def __getattr__(self, _name):
            async def boom(**_kw):
                raise RuntimeError("secondary is down")
            return boom

    shadow._secondary = Exploding()
    ent = await shadow.resolve_or_merge_entity(
        user_id=user_id, project_id=project_id, name="Kai", kind="character",
        source_type="chapter")

    assert ent is not None and ent.canonical_name, "the primary answer did not reach the caller"
    assert shadow.stats.errored.get("resolve_or_merge_entity") == 1
    assert shadow.stats.observations("resolve_or_merge_entity") == 0, (
        "a secondary crash counted as a comparison"
    )
