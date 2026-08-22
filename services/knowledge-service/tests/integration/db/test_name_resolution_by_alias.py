"""T81 — resolving a name through the ALIAS half of `find_entities_by_name`.

⚠️ **Found by bite C: deleting the alias half of the query left the whole suite green.**
`_FIND_BY_NAME_CYPHER_*` resolves on `e.canonical_name = $canonical_name OR $name IN e.aliases`,
and cutting it down to the canonical half alone — so an entity can only ever be found under its
own current name — broke nothing that anyone was testing.

Nothing caught it because `merge_entity` seeds `aliases = [$name]` on create, so for a
freshly-extracted entity **both** halves match the same node and arm 1 alone is enough. The
alias half only earns its keep once name and alias diverge, which is exactly what a rename or a
merge produces:

    merge_entity("Kai")              canonical_name "kai", aliases ["Kai"]   -> either arm finds it
    ...renamed to "Kai Zhou"         canonical_name "kai zhou", aliases ["Kai", "Kai Zhou"]
                                     -> "Kai" now resolves ONLY through the alias arm

That is the case the feature exists for, and it had no test. A reader looking for "Kai" after
the author renamed the character gets nothing back, and nothing in the graph looks wrong.

The second and third tests below are the ordinary contract of the query rather than bites:
one row per entity, and two genuinely different entities not collapsed into one. §10.1
collapsed this query from `CALL { … UNION … }` into a single `MATCH` with an `OR` (AGE has no
subquery, and Cypher cannot `ORDER BY` after a top-level `UNION`), and `UNION` had been doing
the dedup. Neo4j's planner happens to rewrite the `OR` into a union that already dedupes by
node identity — measured, so `RETURN DISTINCT` is belt-and-braces here rather than a fix — but
relying on a planner rewrite for a correctness property is the kind of implicit dependency this
plan keeps finding the hard way, and another engine's `OR` need not behave the same.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio


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


@pytest.mark.parametrize("include_archived", [False, True], ids=["active", "all"])
@pytest.mark.asyncio
async def test_an_entity_is_found_by_an_ALIAS_that_is_not_its_canonical_name(
    neo4j_driver, test_user, include_archived,
):
    """The bite-C case: name and alias have diverged, so only the alias arm can match.

    Both twins are checked. `_FIND_BY_NAME_CYPHER_ACTIVE` and `_FIND_BY_NAME_CYPHER_ALL` differ
    by one line (`e.archived_at IS NULL`) and were 24-line near-duplicates before §10.1 merged
    their arms; a predicate lost from one and kept in the other is precisely what that shape
    hid.
    """
    from app.db.neo4j_repos.entities import (
        find_entities_by_name,
        merge_entity,
        update_entity_fields,
    )

    proj = f"p-{uuid.uuid4().hex[:8]}"
    old_name = f"Kai{uuid.uuid4().hex[:6]}"
    new_name = f"{old_name} Zhou"
    async with neo4j_driver.session() as session:
        created = await merge_entity(session, user_id=test_user, project_id=proj,
                                     name=old_name, kind="person", source_type="chapter")

    async with neo4j_driver.session() as session:
        # The rename an author performs. `aliases` keeps the old spelling; `canonical_name`
        # moves to the new one, so the two halves of the OR now disagree.
        await update_entity_fields(
            session=session, user_id=test_user, entity_id=created.id,
            name=new_name, kind=None, aliases=[old_name, new_name], expected_version=1,
        )

    async with neo4j_driver.session() as session:
        row = await (await session.run(
            "MATCH (e:Entity {id: $id}) RETURN e.canonical_name AS cn, e.aliases AS al",
            id=created.id,
        )).single()
        assert old_name not in (row["cn"],), (
            f"fixture is wrong — canonical_name is still {row['cn']!r}, so the canonical arm "
            f"would find the entity and the alias arm would not be exercised"
        )
        assert old_name in row["al"], (
            f"fixture is wrong — {old_name!r} is not in the alias list {row['al']!r}"
        )

        found = await find_entities_by_name(
            session, user_id=test_user, project_id=proj, name=old_name,
            include_archived=include_archived,
        )
        assert [e.id for e in found] == [created.id], (
            f"the OLD name no longer resolves to the entity that still carries it as an alias "
            f"(got {[e.id for e in found]}). Every reference to the character written before "
            f"the rename now resolves to nothing, and the graph looks perfectly healthy."
        )


@pytest.mark.asyncio
async def test_an_entity_matching_BOTH_arms_resolves_to_ONE_row(neo4j_driver, test_user):
    """The ordinary case, and the reason the query says `RETURN DISTINCT`.

    A `merge_entity`-created node has its own name as canonical name AND as its first alias, so
    both halves of the `OR` match it. `UNION` deduplicated that; the collapsed form must too.
    """
    from app.db.neo4j_repos.entities import find_entities_by_name, merge_entity

    proj = f"p-{uuid.uuid4().hex[:8]}"
    name = f"Kai{uuid.uuid4().hex[:6]}"
    async with neo4j_driver.session() as session:
        created = await merge_entity(session, user_id=test_user, project_id=proj,
                                     name=name, kind="person", source_type="chapter")
        row = await (await session.run(
            "MATCH (e:Entity {id: $id}) RETURN e.aliases AS al", id=created.id,
        )).single()
        assert name in row["al"], (
            f"fixture is wrong — {row['al']!r} does not contain the name, so only one arm "
            f"matches and the test proves nothing about dedup"
        )

        found = await find_entities_by_name(
            session, user_id=test_user, project_id=proj, name=name)
        assert [e.id for e in found] == [created.id], (
            f"name resolution returned {len(found)} rows for one entity — the caller sees two "
            f"candidates where there is one, which is what entity resolution exists to prevent"
        )


@pytest.mark.asyncio
async def test_dedup_does_not_COLLAPSE_two_genuinely_different_entities(
    neo4j_driver, test_user,
):
    """The other direction, on a case the dedup was not derived from: two nodes resolving from
    the same string is the real, intended output of this query — it is what the
    anchored-above-discovered ranking in the `ORDER BY` exists to sort."""
    from app.db.neo4j_repos.entities import find_entities_by_name, merge_entity

    proj = f"p-{uuid.uuid4().hex[:8]}"
    name = f"Rin{uuid.uuid4().hex[:6]}"
    async with neo4j_driver.session() as session:
        a = await merge_entity(session, user_id=test_user, project_id=proj,
                               name=name, kind="person", source_type="chapter")
        b = await merge_entity(session, user_id=test_user, project_id=proj,
                               name=name, kind="place", source_type="chapter")
        assert a.id != b.id, "fixture is wrong — the two kinds must hash to different nodes"

        found = await find_entities_by_name(
            session, user_id=test_user, project_id=proj, name=name)
        assert sorted(e.id for e in found) == sorted([a.id, b.id]), (
            "the dedup collapsed two genuinely different entities that share a name — the "
            "person and the place are separate nodes and resolution must offer both"
        )


@pytest.mark.asyncio
async def test_a_VARIANT_spelling_resolves_through_the_CANONICAL_half(neo4j_driver, test_user):
    """⚠️ Added because bite D — deleting the CANONICAL half instead — also went green.

    Every fixture above is satisfiable by the alias arm alone, because `merge_entity` puts the
    name in the alias list. The canonical arm earns its keep on the case the alias list cannot
    cover: a spelling the caller typed that canonicalises onto the stored form but is not
    literally stored anywhere.

        stored     name "张济"      canonical_name "张济"    aliases ["张济"]
        searched   "張濟"           canonicalises to "张济"  -> NOT in aliases

    This is the simplified/traditional dedup class the dev graph is full of — 17 groups share a
    canonical name across two glossary anchors, and every one of them is CJK (T35). Without the
    canonical arm a reader searching the traditional spelling of a character finds nothing.
    """
    from app.db.neo4j_repos.entities import find_entities_by_name, merge_entity

    proj = f"p-{uuid.uuid4().hex[:8]}"
    stored, variant = "张济", "張濟"
    async with neo4j_driver.session() as session:
        created = await merge_entity(session, user_id=test_user, project_id=proj,
                                     name=stored, kind="person", source_type="chapter")
        row = await (await session.run(
            "MATCH (e:Entity {id: $id}) RETURN e.aliases AS al", id=created.id,
        )).single()
        assert variant not in row["al"], (
            f"fixture is wrong — {variant!r} is in the alias list {row['al']!r}, so the alias "
            f"arm would find it and the canonical arm would not be exercised"
        )

        found = await find_entities_by_name(
            session, user_id=test_user, project_id=proj, name=variant)
        assert [e.id for e in found] == [created.id], (
            f"the traditional spelling {variant!r} did not resolve to the entity stored as "
            f"{stored!r} (got {[e.id for e in found]}) — the canonical arm is what maps one "
            f"onto the other, and the alias list never contains the variant"
        )
