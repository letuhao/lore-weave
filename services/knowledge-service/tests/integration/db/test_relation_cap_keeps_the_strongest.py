"""T82 — the relation cap must keep the STRONGEST edges, not an arbitrary 200.

⚠️ **Found by bite 1.** §10.1 collapsed `get_entity_with_relations` and its glossary-FK twin
from two `CALL { }` subqueries into one aggregation, which moves the `LIMIT` from inside the
subquery to a list slice. A slice takes the FRONT of the list, so the ordering has to be
established before the aggregation and survive it. Deleting the `ORDER BY` — so the cap keeps
whatever order storage happened to yield — left the whole suite green.

Measured on both engines before the rewrite was written, four edges with confidences
`[0.1, 0.9, 0.5, 0.7]`:

    with `WITH e, r ORDER BY r.c DESC` first     Neo4j [0.9, 0.7, 0.5, 0.1]   AGE [0.9, 0.7, 0.5, 0.1]
    aggregating with no ORDER BY at all          Neo4j [0.7, 0.5, 0.9, 0.1]   AGE [0.1, 0.9, 0.5, 0.7]

Both engines keep an order they were asked for, and neither invents one. So this is not a
Neo4j-vs-AGE difference — it is a property that has to be asked for on both, and nothing was
checking that it had been.

The failure is a silent absence, like every other one this run has found: the detail panel
shows `rel_cap` relations and a total, so an author looking at a heavily-connected character
sees 200 arbitrary relations where they should see the 200 strongest, and the count above them
is still correct.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

#: Deliberately tiny, so the cap bites on a fixture small enough to reason about.
_CAP = 3
_CONFIDENCES = [0.10, 0.90, 0.50, 0.70, 0.30]


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n", user_id=user_id,
            )


async def _anchor_with_edges(session, *, user_id, project_id, glossary_entity_id=None):
    """One entity with five outgoing relations of known, deliberately unsorted confidences."""
    from app.db.neo4j_repos.entities import merge_entity
    from app.db.neo4j_repos.relations import create_relation

    tag = uuid.uuid4().hex[:6]
    anchor = await merge_entity(session, user_id=user_id, project_id=project_id,
                                name=f"Anchor{tag}", kind="person", source_type="chapter")
    if glossary_entity_id is not None:
        await session.run(
            "MATCH (e:Entity {id: $id, user_id: $u}) SET e.glossary_entity_id = $g",
            id=anchor.id, u=user_id, g=glossary_entity_id,
        )
    for i, conf in enumerate(_CONFIDENCES):
        peer = await merge_entity(session, user_id=user_id, project_id=project_id,
                                  name=f"Peer{tag}{i}", kind="person", source_type="chapter")
        rel = await create_relation(session, user_id=user_id, subject_id=anchor.id,
                                    predicate=f"knows_{i}", object_id=peer.id,
                                    confidence=conf)
        assert rel is not None, "fixture is wrong — the relation was not created"
    return anchor


def _confidences(detail) -> list[float]:
    return [round(float(e.confidence), 2) for e in detail.relations]


@pytest.mark.asyncio
async def test_the_detail_cap_keeps_the_HIGHEST_confidence_relations(neo4j_driver, test_user):
    from app.db.neo4j_repos.entities import get_entity_with_relations

    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        anchor = await _anchor_with_edges(session, user_id=test_user, project_id=proj)

        detail = await get_entity_with_relations(
            session, user_id=test_user, entity_id=anchor.id, rel_cap=_CAP)
        assert detail is not None

        got = _confidences(detail)
        expected = sorted(_CONFIDENCES, reverse=True)[:_CAP]
        assert got == expected, (
            f"the cap kept {got} instead of the strongest {expected}. The slice takes the "
            f"FRONT of the collected list, so without the `ORDER BY` before the aggregation "
            f"the detail panel shows an arbitrary subset and calls it the top {_CAP}."
        )
        assert detail.total_relations == len(_CONFIDENCES), (
            f"the total must be the FULL count, not the capped length: "
            f"{detail.total_relations} != {len(_CONFIDENCES)}"
        )
        assert detail.relations_truncated is True, (
            "the cap fired but the truncation flag is false — the FE would render "
            "`all N relations` over a list that is missing most of them"
        )


@pytest.mark.asyncio
async def test_the_glossary_FK_twin_caps_the_same_way(neo4j_driver, test_user):
    """The two queries were collapsed together and are one edit apart; a cap that ordered in
    one and not the other is exactly what near-duplicate queries hide."""
    from app.db.neo4j_repos.entities import get_neighborhood_by_glossary_id

    proj = f"p-{uuid.uuid4().hex[:8]}"
    gid = f"gl-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        await _anchor_with_edges(session, user_id=test_user, project_id=proj,
                                 glossary_entity_id=gid)

        detail = await get_neighborhood_by_glossary_id(
            session, user_id=test_user, glossary_entity_id=gid, project_id=proj,
            rel_cap=_CAP)
        assert detail is not None, "the anchored entity did not resolve by its glossary FK"

        got = _confidences(detail)
        expected = sorted(_CONFIDENCES, reverse=True)[:_CAP]
        assert got == expected, (
            f"the glossary-FK neighbourhood kept {got} instead of the strongest {expected} — "
            f"the wiki renderer shows an arbitrary subset of a character's relations"
        )
        assert detail.total_relations == len(_CONFIDENCES)


@pytest.mark.asyncio
async def test_an_entity_with_NO_relations_still_returns_a_row(neo4j_driver, test_user):
    """The other half of what the two subqueries were for: `collect()` over an `OPTIONAL MATCH`
    miss collects a `null`, so the list is filtered AFTER aggregating. Filtering before would
    drop the row and the detail endpoint would 404 an entity that exists."""
    from app.db.neo4j_repos.entities import get_entity_with_relations, merge_entity

    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        lonely = await merge_entity(session, user_id=test_user, project_id=proj,
                                    name=f"Lonely{uuid.uuid4().hex[:6]}", kind="person",
                                    source_type="chapter")
        detail = await get_entity_with_relations(
            session, user_id=test_user, entity_id=lonely.id, rel_cap=_CAP)
        assert detail is not None, (
            "an entity with no relations returned no row at all — the aggregation dropped it"
        )
        assert detail.relations == [] and detail.total_relations == 0, (
            f"expected an empty relation list, got {detail.relations!r} "
            f"(a `[null]` here means the null filter is gone)"
        )
