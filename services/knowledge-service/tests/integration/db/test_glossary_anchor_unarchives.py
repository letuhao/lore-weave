"""T77 — re-syncing a glossary anchor UN-ARCHIVES it, and nothing tested that.

⚠️ Found by bite 49: deleting `e.archived_at = NULL` from `_UPSERT_ANCHOR_CYPHER` — so a
re-synced anchor stays archived forever — left the whole suite green.

The rule is the exact COUNTERPART of `test_merge_never_assign_invariants.py`. That file pins
the queries which must **never** assign `archived_at`, because doing so un-archives a node on
every re-extraction. This one pins the query that **must** assign it, because the glossary
asserting an entity exists is precisely a statement that it is live again.

Two adjacent queries, one field, opposite policies:

    _GLOSSARY_ANCHOR_SYNC_CYPHER   archived_at was ON CREATE ONLY  -> must NOT assign  (T76)
    _UPSERT_ANCHOR_CYPHER          archived_at was in BOTH arms    -> MUST assign      (T77)

which is why the never-assign list is per-query rather than per-field, and why a rule stated
over "every merge query" would have been wrong.
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


@pytest.mark.asyncio
async def test_a_glossary_RESYNC_revives_an_archived_anchor(neo4j_driver, test_user):
    from app.db.neo4j_repos.entities import (
        archive_entity,
        get_entity,
        upsert_glossary_anchor_counted,
    )

    proj = f"p-{uuid.uuid4().hex[:8]}"
    gid = f"g-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        anchor, created = await upsert_glossary_anchor_counted(
            session, user_id=test_user, project_id=proj, glossary_entity_id=gid,
            name="Kai", kind="character", aliases=[], canonical_version=1,
        )
        assert created is True, "the first upsert must report was_created"

        await archive_entity(session, user_id=test_user, canonical_id=anchor.id,
                             reason="user_deleted")
        archived = await get_entity(session, user_id=test_user, canonical_id=anchor.id)
        assert archived is not None and archived.archived_at is not None, (
            "fixture is wrong — the anchor should be archived before the re-sync"
        )

        # The glossary re-asserts the entity. That is a statement it exists.
        _, created_again = await upsert_glossary_anchor_counted(
            session, user_id=test_user, project_id=proj, glossary_entity_id=gid,
            name="Kai", kind="character", aliases=[], canonical_version=1,
        )
        assert created_again is False, (
            "was_created must be False on the second upsert — the pre-MATCH count is what "
            "reports it now that the `__was_created` marker is gone (T77)"
        )

        revived = await get_entity(session, user_id=test_user, canonical_id=anchor.id)
        assert revived is not None and revived.archived_at is None, (
            "a glossary re-sync left the anchor ARCHIVED — the upsert must clear "
            "`archived_at`, or an entity the glossary still asserts stays invisible to every "
            "read that filters archived nodes out"
        )
