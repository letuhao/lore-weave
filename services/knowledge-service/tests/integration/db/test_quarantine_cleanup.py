"""K15.10 quarantine cleanup job — integration tests vs live Neo4j.

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id and DETACH DELETEs in finally.

Acceptance (plan row K15.10):
  - Old quarantined facts get invalidated (valid_until set)
  - Recent quarantined facts untouched
  - Non-quarantined facts untouched
  - `quarantine_auto_invalidated_total` metric incremented
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.facts import merge_fact
from app.jobs.quarantine_cleanup import run_quarantine_cleanup
from app.metrics import quarantine_auto_invalidated_total


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-k15-10-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n",
                user_id=user_id,
            )


async def _backdate_fact(driver, *, user_id: str, fact_id: str, hours: int):
    """Nudge `updated_at` N hours into the past so the cleanup TTL
    fires on the next run. merge_fact always stamps `datetime()`;
    we bypass it here to simulate a fact that sat in quarantine."""
    async with driver.session() as raw:
        await raw.run(
            "MATCH (f:Fact {id: $id}) WHERE f.user_id = $user_id "
            "SET f.updated_at = datetime() - duration({hours: $hours})",
            id=fact_id,
            user_id=user_id,
            hours=hours,
        )


@pytest.mark.asyncio
async def test_k15_10_old_quarantined_fact_invalidated(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as raw:
        fact = await merge_fact(
            raw,
            user_id=test_user,
            project_id="p-1",
            type="negation",
            content="Kai does not know Zhao",
            confidence=0.5,
            pending_validation=True,
            source_type="chapter",
        )
    await _backdate_fact(
        neo4j_driver, user_id=test_user, fact_id=fact.id, hours=25,
    )

    async with neo4j_driver.session() as raw:
        invalidated = await run_quarantine_cleanup(
            raw, user_id=test_user, ttl_hours=24,
        )
    assert invalidated == 1

    async with neo4j_driver.session() as raw:
        result = await raw.run(
            "MATCH (f:Fact {id: $id}) RETURN f.valid_until AS vu",
            id=fact.id,
        )
        record = await result.single()
    assert record is not None
    assert record["vu"] is not None


@pytest.mark.asyncio
async def test_k15_10_fresh_quarantined_fact_untouched(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as raw:
        fact = await merge_fact(
            raw,
            user_id=test_user,
            project_id="p-1",
            type="negation",
            content="Fresh pending fact",
            confidence=0.5,
            pending_validation=True,
            source_type="chapter",
        )

    async with neo4j_driver.session() as raw:
        invalidated = await run_quarantine_cleanup(
            raw, user_id=test_user, ttl_hours=24,
        )
    assert invalidated == 0

    async with neo4j_driver.session() as raw:
        result = await raw.run(
            "MATCH (f:Fact {id: $id}) RETURN f.valid_until AS vu",
            id=fact.id,
        )
        record = await result.single()
    assert record["vu"] is None


@pytest.mark.asyncio
async def test_k15_10_promoted_fact_untouched_even_if_old(
    neo4j_driver, test_user
):
    """A fact that Pass 2 already promoted (pending_validation=false)
    must NOT be invalidated by the quarantine sweeper, even if it's
    older than the TTL."""
    async with neo4j_driver.session() as raw:
        fact = await merge_fact(
            raw,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Kai decided to stay",
            confidence=0.9,
            pending_validation=False,
            source_type="chapter",
        )
    await _backdate_fact(
        neo4j_driver, user_id=test_user, fact_id=fact.id, hours=100,
    )

    async with neo4j_driver.session() as raw:
        invalidated = await run_quarantine_cleanup(
            raw, user_id=test_user, ttl_hours=24,
        )
    assert invalidated == 0


@pytest.mark.asyncio
async def test_k15_10_already_invalidated_fact_untouched(
    neo4j_driver, test_user
):
    """Idempotency: running the job twice must not double-touch a
    fact that was already invalidated on the first run."""
    async with neo4j_driver.session() as raw:
        fact = await merge_fact(
            raw,
            user_id=test_user,
            project_id="p-1",
            type="negation",
            content="Stale quarantine",
            confidence=0.5,
            pending_validation=True,
            source_type="chapter",
        )
    await _backdate_fact(
        neo4j_driver, user_id=test_user, fact_id=fact.id, hours=30,
    )

    async with neo4j_driver.session() as raw:
        first = await run_quarantine_cleanup(
            raw, user_id=test_user, ttl_hours=24,
        )
    async with neo4j_driver.session() as raw:
        second = await run_quarantine_cleanup(
            raw, user_id=test_user, ttl_hours=24,
        )
    assert first == 1
    assert second == 0


@pytest.mark.asyncio
async def test_k15_10_metric_incremented(neo4j_driver, test_user):
    async with neo4j_driver.session() as raw:
        fact = await merge_fact(
            raw,
            user_id=test_user,
            project_id="p-1",
            type="negation",
            content="Metric probe fact",
            confidence=0.5,
            pending_validation=True,
            source_type="chapter",
        )
    await _backdate_fact(
        neo4j_driver, user_id=test_user, fact_id=fact.id, hours=48,
    )

    before = quarantine_auto_invalidated_total._value.get()
    async with neo4j_driver.session() as raw:
        await run_quarantine_cleanup(
            raw, user_id=test_user, ttl_hours=24,
        )
    after = quarantine_auto_invalidated_total._value.get()
    assert after - before >= 1


@pytest.mark.asyncio
async def test_k15_10_invalid_ttl_raises(neo4j_driver, test_user):
    async with neo4j_driver.session() as raw:
        with pytest.raises(ValueError):
            await run_quarantine_cleanup(
                raw, user_id=test_user, ttl_hours=0,
            )
