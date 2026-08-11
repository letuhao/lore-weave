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
    # Both were `NotImplementedError` until 2026-08-12 and are now real, which is what takes
    # the comparison from 7 of 9 operations to nine. They are still driven explicitly: an
    # operation nobody called and an operation that cannot answer look identical in a report
    # that only counts successes.
    await store.status_at_order(
        user_id=user_id, project_id=project_id, entity_ids=[a.id], at_order=10)
    await store.events_in_window(user_id=user_id, project_id=project_id)


# ── the identity mapping closed the id-keyed gap ────────────────────────────────────────
#
# The first shadow run reported `archive_entity`, `restore_entity`, `upsert_relation` and
# `relations_for` as DIVERGED with `secondary=None`, and none of those was an engine
# difference: each engine mints its OWN node id, so the shadow handed the secondary a node it
# had never seen. `ShadowGraphStore` now learns a primary->secondary id mapping from
# `resolve_or_merge_entity` — the one operation keyed on NATURAL identity, and therefore the
# only place the two engines can be known to be discussing the same entity — and substitutes
# it into every id-keyed replay.
#
# The exemption list this file used to carry is GONE, deliberately. An exemption would have
# made the report look clean while 6 of 9 operations stayed uncompared;
# `D-T43-ID-KEYED-OPS-NEED-A-MAPPING` asked for the mapping precisely so the comparison
# becomes real rather than narrower.
# ⚠️ EMPTY, and that is the point of this cycle. `D-T42-AGE-EVENT-SURFACE` is closed: AGE now
# implements `status_at_order` and `events_in_window`, so nothing is `uncovered` and the
# coverage floor has nothing left to block on. If either regresses to a raise, this set is
# where the expectation lives and the floor test reds immediately.
_UNIMPLEMENTED: set[str] = set()


async def test_the_two_engines_agree_on_every_comparable_operation(shadow):
    """The differential run, over the operations that CAN be compared.

    A divergence outside `_ID_KEYED` is a real finding about the engines and fails here with
    its samples attached.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    await _traffic(shadow, user_id, project_id)
    report = shadow.coverage_report()

    diverged = {op: r for op, r in report["operations"].items() if r["diverged"]}
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

    As of 2026-08-12 the floor is EMPTY — every one of the nine operations is compared. The
    assertion is kept (rather than deleted as satisfied) because it is what reds if an
    operation regresses to a raise, or if a future port method arrives with no adapter behind
    it: `OPERATIONS` is the checklist, and an unobserved entry blocks cutover.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    await _traffic(shadow, user_id, project_id)
    report = shadow.coverage_report()

    assert set(report["blocked_by"]) == _UNIMPLEMENTED, (
        f"unexpected coverage floor: {report['blocked_by']}"
    )
    # ⚠️ `cutover_permitted` is a DATA statement, not an authorisation. It says the shadow
    # has no remaining objection: every operation was compared and none disagreed. Whether
    # the swap HAPPENS is QC-7's POST-REVIEW checkpoint and the PO's call on sealed rows
    # T1/T2 — a harness that could authorise its own cutover would be the plan's
    # stop-and-wait discipline written out of existence.
    assert report["cutover_permitted"] is True, (
        f"the shadow still objects: blocked_by={report['blocked_by']} "
        f"samples={report['samples']}"
    )
    for op in OPERATIONS:
        if op not in report["blocked_by"]:
            assert report["operations"][op]["observations"] > 0


async def test_an_unimplemented_secondary_is_uncovered_not_agreed(shadow):
    """The three-outcome rule, tested against a STUB rather than against AGE's gaps.

    It used to lean on `AgeGraphStore.status_at_order` raising. That gap closed this cycle,
    and a rule that stops being tested the moment the codebase improves is a rule that will
    be gone when it is next needed. A stub keeps it permanently exercised.

    Why the rule matters: if the shadow folded `NotImplementedError` into `agreed`, a method
    the secondary CANNOT ANSWER would count toward parity — a coverage gap reading as a data
    result, which is exactly what the raise exists to prevent.
    """
    class Refusing:
        def __getattr__(self, _name):
            async def _raise(**_kw):
                raise NotImplementedError("not built on this engine")
            return _raise

    shadow._secondary = Refusing()
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
