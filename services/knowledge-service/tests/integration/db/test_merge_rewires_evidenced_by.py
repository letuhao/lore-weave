"""T74 — merging two entities must MOVE the loser's evidence, first-writer-wins.

⚠️ This file exists because bites 42 and 43 found the rewire had **no coverage at all**. The
loop could be emptied (`for … in []`) or its dedup disabled and the whole integration suite
stayed green. Merging two entities and silently dropping the loser's `:EVIDENCED_BY` edges is a
data-loss bug that nothing would have caught — and the edges are load-bearing: the zero-evidence
sweeper deletes any node whose last one goes.

The operation is `(ExtractionSource, job_id)`-keyed and FIRST-writer-wins: an edge the target
already has keeps its own properties. §10.3 rebuilt it as three statements in one transaction
because the original `ON CREATE SET e2 = props` is the one whole-map branch `coalesce` cannot
express, and the naive unconditional `SET` reverses that rule on BOTH engines.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    """Local, like every other DB test file here — the fixture is not in conftest."""
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n", user_id=user_id,
            )


@pytest.mark.asyncio
async def test_merge_MOVES_the_losers_evidence_and_keeps_the_winners_own(neo4j_driver, test_user):
    from app.db.graph_repos.entities import merge_entities, merge_entity
    from app.db.graph_repos.provenance import (
        list_evidence_for_target,
        upsert_extraction_source,
    )
    from app.db.graph_repos.provenance import add_evidence

    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        loser = await merge_entity(session, user_id=test_user, project_id=proj, name="Kai",
                                   kind="person", source_type="chapter", auto_created=True)
        winner = await merge_entity(session, user_id=test_user, project_id=proj, name="Kai Zhou",
                                    kind="person", source_type="chapter", auto_created=True)

        src_a = await upsert_extraction_source(
            session, user_id=test_user, project_id=proj,
            source_type="chapter", source_id="ch-1")
        src_b = await upsert_extraction_source(
            session, user_id=test_user, project_id=proj,
            source_type="chapter", source_id="ch-2")

        # The loser has evidence from BOTH sources.
        await add_evidence(session, user_id=test_user, target_label="Entity",
                           target_id=loser.id, source_id=src_a.id, job_id="job-1",
                           extraction_model="m", confidence=0.9)
        await add_evidence(session, user_id=test_user, target_label="Entity",
                           target_id=loser.id, source_id=src_b.id, job_id="job-2",
                           extraction_model="m", confidence=0.9)
        # The winner ALREADY has one for (src_a, job-1) — the overlapping case, which is the
        # only one that can tell first-writer-wins from last-writer-wins.
        await add_evidence(session, user_id=test_user, target_label="Entity",
                           target_id=winner.id, source_id=src_a.id, job_id="job-1",
                           extraction_model="m", confidence=0.9)

        before = await list_evidence_for_target(
            session, user_id=test_user, target_label="Entity", target_id=winner.id)
        assert len(before) == 1, "fixture is wrong — the winner should start with exactly one"

        await merge_entities(session, user_id=test_user,
                             source_id=loser.id, target_id=winner.id)

        after = await list_evidence_for_target(
            session, user_id=test_user, target_label="Entity", target_id=winner.id)
        pairs = sorted((e.source_id, e.job_id) for e in after)

        # Bite 42: an empty rewire loses `job-2` entirely, and with it the only evidence
        # tying the winner to ch-2 — the sweeper would then be free to delete on the next pass.
        assert (src_b.id, "job-2") in pairs, (
            f"the loser's (ch-2, job-2) evidence was NOT moved onto the winner: {pairs}"
        )
        # Bite 43: without the dedup, (src_a, job-1) appears TWICE.
        assert len(pairs) == len(set(pairs)), (
            f"duplicate EVIDENCED_BY edges after merge: {pairs} — the rewire must not "
            f"recreate one the winner already had"
        )
        assert len(pairs) == 2, f"expected exactly ch-1/job-1 and ch-2/job-2, got {pairs}"
