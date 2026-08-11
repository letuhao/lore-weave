"""T35 — opaque identity: a rename must not mint a duplicate.

The plan's own acceptance test, written as a test:

    rename + re-kind → no stale node, no minted duplicate

WHY IT FAILED BEFORE. `Entity.id` is `entity_canonical_id(user, project, name,
kind)` — a hash of the canonicalised NAME and KIND — and `merge_entity` MERGEs
on that id. So the moment an author renames an entity through the glossary (a
path that correctly MERGEs on `glossary_entity_id` and leaves `e.id` alone), the
node's stored id no longer equals the hash of its own current name. The next
extraction that sees the NEW name computes a NEW hash, finds nothing at that id,
and mints a second node for the same character.

Nothing raises. Both nodes are well-formed. The graph simply has two of
somebody, and every edge written afterwards attaches to whichever one the
writer happened to compute.

Measured on the dev graph 2026-08-11: 2819 of 6297 nodes carry an id that
disagrees with a recompute — 2818 of them glossary-anchored, which is exactly
the population the rename path touches.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import link_to_glossary, merge_entity


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-t35-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $u DETACH DELETE n", u=user_id,
            )


async def _count(session, user_id, project_id):
    res = await session.run(
        "MATCH (e:Entity {user_id: $u, project_id: $p}) RETURN count(e) AS n",
        u=user_id, p=project_id,
    )
    rec = await res.single()
    return rec["n"]


@pytest.mark.asyncio
async def test_rename_then_reextract_does_not_mint_a_duplicate(neo4j_driver, test_user):
    """THE acceptance test. Extraction creates 'Kai'; the author renames it to
    'Kai Sr.' through the glossary; extraction sees the new name in later prose.
    One character must remain one node."""
    P = "p-t35"
    async with neo4j_driver.session() as session:
        first = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Kai", kind="character", source_type="book_content")
        assert await _count(session, test_user, P) == 1

        # The author renames through the glossary. `link_to_glossary` is the
        # documented rename path: it looks the node up BY canonical_id and
        # updates in place, and its own docstring records that "the id stays
        # stable post-rename — it no longer matches
        # entity_canonical_id(new_name, kind), but that's fine". Fine for that
        # function; the extraction writer is what it is not fine for.
        renamed = await link_to_glossary(
            session, user_id=test_user, canonical_id=first.id,
            glossary_entity_id="g-kai", name="Kai Sr.", kind="character",
            aliases=["Kai"])
        assert renamed is not None

        # Extraction runs again over later chapters and reads the NEW name.
        again = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Kai Sr.", kind="character", source_type="book_content")

        assert await _count(session, test_user, P) == 1, (
            "a rename minted a SECOND node for the same character — the id is "
            "hash(name, kind) and the rename left the old hash in place")
        assert again.id == first.id, "the surviving node must keep its identity"


@pytest.mark.asyncio
async def test_rekind_does_not_mint_a_duplicate(neo4j_driver, test_user):
    """The other half of the plan's test. A re-kind changes the OTHER hash
    input, so it fails the same way for a different reason — and this is the
    path the 2026-08-02 backfill actually took."""
    P = "p-t35"
    async with neo4j_driver.session() as session:
        first = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Ashfall", kind="location", source_type="book_content")
        renamed = await link_to_glossary(
            session, user_id=test_user, canonical_id=first.id,
            glossary_entity_id="g-ash", name="Ashfall", kind="faction")
        assert renamed is not None

        again = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Ashfall", kind="faction", source_type="book_content")

        assert await _count(session, test_user, P) == 1, (
            "a re-kind minted a SECOND node — same defect, other hash input")
        assert again.id == first.id


@pytest.mark.asyncio
async def test_distinct_entities_still_get_distinct_nodes(neo4j_driver, test_user):
    """The control. A fix that collapses everything would pass the two tests
    above and destroy the graph — two genuinely different characters must stay
    two nodes, and the same name under a different KIND is a different entity."""
    P = "p-t35"
    async with neo4j_driver.session() as session:
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Kai", kind="character", source_type="book_content")
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Bob", kind="character", source_type="book_content")
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Kai", kind="location", source_type="book_content")
        assert await _count(session, test_user, P) == 3


@pytest.mark.asyncio
async def test_projects_stay_isolated(neo4j_driver, test_user):
    """The tenancy control: the same name in two projects is two nodes, and a
    name-based resolution must not reach across the project boundary."""
    async with neo4j_driver.session() as session:
        await merge_entity(session, user_id=test_user, project_id="p-a",
                           name="Kai", kind="character", source_type="book_content")
        await merge_entity(session, user_id=test_user, project_id="p-b",
                           name="Kai", kind="character", source_type="book_content")
        assert await _count(session, test_user, "p-a") == 1
        assert await _count(session, test_user, "p-b") == 1


@pytest.mark.asyncio
async def test_a_node_at_the_derived_id_still_wins(neo4j_driver, test_user):
    """THE SAFETY PROPERTY. Resolution must only decide anything when no node
    sits at the derived id — otherwise this change silently moves extraction
    writes between nodes that share a canonical name.

    That is not hypothetical: the dev graph has 17 groups sharing
    (user, project, canonical_name, kind) and ALL 17 are multi-ANCHORED — two
    distinct glossary entities whose names canonicalise together, each mirrored
    to its own node. A bare "oldest wins" would have re-pointed those writes.
    """
    from app.db.neo4j_repos.canonical import entity_canonical_id

    P = "p-t35"
    derived = entity_canonical_id(
        user_id=test_user, project_id=P, name="Kai", kind="character")
    async with neo4j_driver.session() as session:
        # The node at the derived id — what a normal extraction write creates.
        at_derived = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Kai", kind="character", source_type="book_content")
        assert at_derived.id == derived
        # ...and an OLDER node sharing the canonical key but NOT at the derived
        # id. This is the shape of all 17 live collision groups: a second
        # anchored node whose stored id was computed under earlier
        # canonicalisation rules.
        await session.run(
            "CREATE (e:Entity {id: $id, user_id: $u, project_id: $p, "
            "name: 'Kai', canonical_name: 'kai', kind: 'character', "
            "aliases: ['Kai'], source_types: ['glossary'], provenances: [], "
            "confidence: 1.0, version: 1, created_at: datetime('2000-01-01T00:00:00Z'), "
            "updated_at: datetime()})",
            id="decoy-older-node", u=test_user, p=P)

        # A second extraction write must land on the DERIVED node, not the older decoy.
        again = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Kai", kind="character", source_type="book_content")
        assert again.id == derived, (
            "a node at the derived id must still win — otherwise this change "
            "re-points writes for every canonical-name collision in the graph")
        assert await _count(session, test_user, P) == 2  # decoy untouched
