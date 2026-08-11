"""A migrated call site must return EXACTLY what it returned before (plan T17).

WHY THE UNIT TESTS CANNOT DO THIS
---------------------------------
`tests/unit/test_context.py` patches `get_graph_store` wholesale, so a canned list comes
back and no argument the call site passes ever reaches a store. Measured: changing the
migrated call's `min_confidence` from the port default `0.8` to `0.0` — which lets
low-confidence edges into a set that is **hashed into `build_inputs.kg_neighborhood_hash`**
— left all 14 wiki/context unit tests **green**.

That is the recorded `mocked-client-hides-server-side-filters` trap: those tests prove the
WIRING (the call site reaches the port, degradation still degrades) and cannot prove the
BEHAVIOUR. Both are worth having; only one of them is this.

So the equivalence is asserted where a difference is visible: against a real graph, calling
the OLD path and the NEW path with the same arguments and comparing the results.

WHY EQUIVALENCE AND NOT JUST "THE NEW PATH WORKS"
-------------------------------------------------
T17's entire safety argument is that migrating a call site changes nothing — the adapter is
a passthrough to the same repo function with the same defaults. That claim is falsifiable
and cheap to check, and it is the claim that lets the rest of the 70 modules be migrated as
ordinary reviewable changes rather than as a cutover. If it ever stops holding, the failure
is silent: relations quietly appear or vanish from a hashed set, and every wiki page
false-flags as stale.

    docker run -d --name lw-neo4j-scratch -p 7999:7687 \
      -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community
    TEST_NEO4J_URI=bolt://localhost:7999 pytest tests/integration/db/test_port_migration_equivalence.py
"""
from __future__ import annotations

import uuid

import pytest

from app.adapters.graph_store_provider import get_graph_store
from app.db.neo4j_repos.entities import find_entities_by_name, merge_entity
from app.db.neo4j_repos.relations import create_relation, find_relations_for_entity

pytestmark = pytest.mark.asyncio


async def _fixture_graph(session, user_id: str, project_id: str):
    """Two entities and three edges spanning the defaults that matter.

    The confidences straddle the port's `min_confidence=0.8` on both sides, so a default
    that drifted in EITHER direction changes the returned set — a fixture where every edge
    is confidently above the threshold would pass whatever the default became.
    """
    a = await merge_entity(
        session, user_id=user_id, project_id=project_id, name="Kai",
        kind="character", source_type="chapter")
    b = await merge_entity(
        session, user_id=user_id, project_id=project_id, name="Mira",
        kind="character", source_type="chapter")
    for predicate, confidence in (("ally_of", 0.95), ("rival_of", 0.85), ("maybe", 0.10)):
        await create_relation(
            session, user_id=user_id, subject_id=a.id, object_id=b.id,
            predicate=predicate, confidence=confidence)
    return a, b


async def test_the_port_returns_exactly_what_the_repo_call_returned(neo4j_driver):
    """The migrated wiki call, both ways, same arguments, same result.

    Compared as an ORDERED list of (id, predicate, confidence): the wiki path renders these
    into text and hashes the sorted output, so a set-equality assertion would miss an
    ordering change that still moves the hash.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    async with neo4j_driver.session() as session:
        a, _ = await _fixture_graph(session, user_id, project_id)

        # exactly the arguments app/wiki/context.py::gather_kg_facts passes
        kwargs = dict(user_id=user_id, entity_id=a.id, project_id=project_id, limit=20)

        before = await find_relations_for_entity(session, **kwargs)
        after = await get_graph_store(session).relations_for(**kwargs)

        shape = lambda rels: [(r.id, r.predicate, r.confidence) for r in rels]  # noqa: E731
        assert shape(after) == shape(before), (
            "the port returned a different relation set than the repo call it replaced — "
            "this set is hashed into build_inputs.kg_neighborhood_hash, so a difference "
            "here false-flags every wiki page as stale instead of raising"
        )
        assert before, "the fixture produced no relations — the comparison was vacuous"


async def test_find_entities_by_name_is_equivalent_through_the_port(neo4j_driver):
    """The other method T17 migrated (`context/selectors/facts.py`, 3 call sites).

    Includes the TENANCY case, because that is the one the unit tests provably cannot see:
    changing a migrated call site's `user_id` to a different tenant left all 25 facts-selector
    tests **green** — their fake store ignores the argument entirely. Here a wrong tenant
    returns nothing, which is the whole point of the filter.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    async with neo4j_driver.session() as session:
        await _fixture_graph(session, user_id, project_id)
        store = get_graph_store(session)

        kwargs = dict(user_id=user_id, project_id=project_id, name="Kai")
        before = await find_entities_by_name(session, **kwargs)
        after = await store.find_entities_by_name(**kwargs)
        assert [e.id for e in after] == [e.id for e in before], (
            "the port returned a different entity set than the repo call it replaced"
        )
        assert before, "the fixture resolved no entity — the comparison was vacuous"

        other = await store.find_entities_by_name(
            user_id=f"other-{uuid.uuid4().hex[:8]}", project_id=project_id, name="Kai")
        assert other == [], (
            "another tenant's name lookup returned rows — the user_id predicate is not "
            "reaching the query, and no unit test in this repo can see that"
        )


async def test_the_confidence_default_is_the_one_that_filters(neo4j_driver):
    """Pins WHY the equivalence above is not trivially true.

    The fixture's `maybe` edge sits at 0.10, below the port's `min_confidence=0.8`. If this
    assertion ever fails, the default moved and the previous test's comparison became a
    comparison of two identically-wrong answers — which is how an equivalence test rots
    into a tautology.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    async with neo4j_driver.session() as session:
        a, _ = await _fixture_graph(session, user_id, project_id)
        store = get_graph_store(session)

        default = await store.relations_for(
            user_id=user_id, entity_id=a.id, project_id=project_id, limit=20)
        unfiltered = await store.relations_for(
            user_id=user_id, entity_id=a.id, project_id=project_id, limit=20,
            min_confidence=0.0)

        assert {r.predicate for r in default} == {"ally_of", "rival_of"}
        assert "maybe" in {r.predicate for r in unfiltered}, (
            "the low-confidence edge was not returned even with min_confidence=0.0 — the "
            "fixture is not exercising the filter, so the default cannot be proven to work"
        )
