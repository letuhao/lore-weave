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
from app.db.neo4j_repos.enrichment import upsert_enriched_anchor
from loreweave_extraction.canonical import entity_canonical_id


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


# ── T35 · the ENRICHMENT anchor had the same defect, and a worse consequence ──


@pytest.mark.asyncio
async def test_enrichment_writeback_after_a_rename_does_not_mint_or_STEAL_the_anchor(
    neo4j_driver, test_user
):
    """🔴 The minting defect `merge_entity` fixed was still live on the enrichment
    write-back path, and there it does something worse than duplicate.

    `upsert_enriched_anchor` MERGEd on `entity_canonical_id(user, project, name, kind)`.
    After a glossary rename the real node keeps its old `e.id`, so the recomputed id matches
    nothing and `ON CREATE` mints a second node — the familiar half. The new half is the
    statement that runs FIRST:

        MATCH (stale:Entity {user_id: …, glossary_entity_id: …})
        WHERE stale.id <> $canon_id
        SET stale.glossary_entity_id = NULL

    It exists to free a stale claim before the MERGE, because `:Entity(glossary_entity_id)`
    is UNIQUE. But after a rename **the real entity IS the node it calls stale**, so the
    anchor is stripped off the author's actual character and handed to a freshly minted
    enrichment stub. The glossary's link now points at a node that holds nothing but
    quarantined enrichment facts, and the real node — with every relation, event and fact on
    it — is silently unanchored.

    Nothing raises. Both nodes are well-formed. This is the same shape as the original
    defect and it is asserted on both counts: the COUNT (no duplicate) and, load-bearing,
    WHICH node ends up holding the anchor.
    """
    P = "p-t35-enrich"
    async with neo4j_driver.session() as session:
        first = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Kai", kind="character", source_type="book_content")
        renamed = await link_to_glossary(
            session, user_id=test_user, canonical_id=first.id,
            glossary_entity_id="g-kai-enrich", name="Kai Sr.", kind="character")
        assert renamed is not None
        assert await _count(session, test_user, P) == 1

        # Enrichment write-back sees the entity by its CURRENT name, exactly as
        # `internal_enrichment.py` computes it from the request payload.
        await upsert_enriched_anchor(
            session,
            user_id=test_user,
            glossary_entity_id="g-kai-enrich",
            name="Kai Sr.",
            canon_name="kai sr.",
            kind="character",
            project_id=P,
            anchor_confidence=0.8,
            anchor_source_type="enriched:test",
            origin="enrichment",
            proposal_id="prop-1",
            technique="test",
        )

        assert await _count(session, test_user, P) == 1, (
            "enrichment write-back minted a SECOND node after a rename — it MERGEd on the "
            "recomputed hash, which the renamed node no longer carries")

        res = await session.run(
            "MATCH (e:Entity {user_id: $u, project_id: $p, "
            "glossary_entity_id: 'g-kai-enrich'}) RETURN e.id AS id",
            u=test_user, p=P,
        )
        holders = [r["id"] async for r in res]
        assert holders == [first.id], (
            "the glossary anchor moved OFF the real entity. The 'free the stale claim' "
            "statement treats the renamed node as stale, so a write-back strips the anchor "
            f"from the author's character and gives it to an enrichment stub. holders={holders}")


@pytest.mark.asyncio
async def test_enrichment_anchor_is_still_idempotent_and_still_frees_a_GENUINELY_stale_claim(
    neo4j_driver, test_user
):
    """The two controls a resolve-by-anchor fix must not break.

    A fix that simply stopped freeing stale claims would pass the rename test and trip the
    UNIQUE constraint the first time an anchor genuinely moved between entities — so both
    directions are pinned: re-calling must not duplicate, and a claim held by a DIFFERENT
    entity must still be released.
    """
    P = "p-t35-enrich2"
    common = dict(
        user_id=test_user, glossary_entity_id="g-move", name="Mira", canon_name="mira",
        kind="character", project_id=P, anchor_confidence=0.8,
        anchor_source_type="enriched:test", origin="enrichment",
        proposal_id="prop-2", technique="test",
    )
    async with neo4j_driver.session() as session:
        await upsert_enriched_anchor(session, **common)
        await upsert_enriched_anchor(session, **common)
        assert await _count(session, test_user, P) == 1, "re-calling minted a second anchor"

        # A DIFFERENT entity now claims the same glossary id — the case the free-stale
        # statement exists for. The old holder must be released, not left to trip UNIQUE.
        # A DIFFERENT entity claims the same glossary id. With the derivation inside the
        # repo, the caller expresses that by naming the entity — the derived id for
        # "Mira the Elder" IS `other.id`, because `merge_entity` minted it at that hash and
        # nothing has renamed it. So `byId` resolves to `other` and the anchor moves, which
        # is the deliberate re-anchor the coalesce order protects.
        other = await merge_entity(
            session, user_id=test_user, project_id=P,
            name="Mira the Elder", kind="character", source_type="book_content")
        await upsert_enriched_anchor(
            session,
            **{**common, "name": "Mira the Elder", "canon_name": "mira the elder"},
        )
        res = await session.run(
            "MATCH (e:Entity {user_id: $u, project_id: $p, glossary_entity_id: 'g-move'}) "
            "RETURN e.id AS id",
            u=test_user, p=P,
        )
        holders = [r["id"] async for r in res]
        assert holders == [other.id], (
            f"the anchor did not move to the new claimant, or two nodes hold it: {holders}")
