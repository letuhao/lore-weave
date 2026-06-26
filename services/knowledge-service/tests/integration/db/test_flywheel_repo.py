"""T4.1 integration — the flywheel net-new chain against live Neo4j.

The unit tests mock run_read; THIS test proves the real chain: the Pass-2
writers (merge_entity / merge_event / create_relation) actually STAMP
``created_job_id`` ON CREATE, and ``get_flywheel_delta`` counts exactly the
nodes minted by a given job — an unstamped sibling (a node from another job /
pre-T4.1) is NOT counted. Skipped when TEST_NEO4J_URI is unset.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import merge_entity
from app.db.neo4j_repos.events import merge_event
from app.db.neo4j_repos.relations import create_relation
from app.db.neo4j_repos.flywheel import get_flywheel_delta


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-fly-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            # DETACH on Entity also clears RELATES_TO; Event has no entity edge.
            await session.run("MATCH (e:Entity {user_id: $u}) DETACH DELETE e", u=user_id)
            await session.run("MATCH (v:Event {user_id: $u}) DETACH DELETE v", u=user_id)


@pytest.mark.asyncio
async def test_writers_stamp_job_and_delta_counts_net_new(neo4j_driver, test_user):
    job = f"job-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        # Two entities + an event + a relation MINTED by `job`.
        kael = await merge_entity(
            session, user_id=test_user, project_id="p1", name="FlyKael",
            kind="character", source_type="book_content", job_id=job,
        )
        mira = await merge_entity(
            session, user_id=test_user, project_id="p1", name="FlyMira",
            kind="character", source_type="book_content", job_id=job,
        )
        # An UNSTAMPED sibling (no job_id) — must NOT be counted for `job`.
        await merge_entity(
            session, user_id=test_user, project_id="p1", name="FlyOld",
            kind="character", source_type="book_content",
        )
        await merge_event(
            session, user_id=test_user, project_id="p1", title="The Fly Duel",
            chapter_id="ch1", source_type="book_content", job_id=job,
        )
        await create_relation(
            session, user_id=test_user, subject_id=kael.id, predicate="ALLY_OF",
            object_id=mira.id, confidence=0.9, job_id=job,
        )

        delta = await get_flywheel_delta(session, job_id=job, user_id=test_user)

    # net-new: 2 of the 3 entities (the unstamped sibling excluded)
    assert delta.entities_added == 2, delta.entities_added
    assert delta.events_added == 1, delta.events_added
    assert delta.relations_added == 1, delta.relations_added
    names = {i.name for i in delta.new_items}
    assert {"FlyKael", "FlyMira"} <= names
    assert "FlyOld" not in names  # the unstamped sibling never surfaces
    rel = next(i for i in delta.new_items if i.kind == "relation")
    assert "→ ALLY_OF →" in rel.name


@pytest.mark.asyncio
async def test_delta_is_zero_for_a_job_that_created_nothing(neo4j_driver, test_user):
    # A re-extraction that only MATCHED existing nodes mints nothing → empty delta.
    async with neo4j_driver.session() as session:
        await merge_entity(
            session, user_id=test_user, project_id="p1", name="FlyExisting",
            kind="character", source_type="book_content", job_id="job-A",
        )
        delta = await get_flywheel_delta(session, job_id="job-B", user_id=test_user)
    assert (delta.entities_added, delta.relations_added, delta.events_added) == (0, 0, 0)
    assert delta.new_items == []
