"""K11.7 facts repository — integration tests against live Neo4j."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.facts import (
    FACT_TYPES,
    delete_facts_with_zero_evidence,
    fact_id,
    get_fact,
    invalidate_fact,
    list_facts_by_type,
    merge_fact,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (f:Fact {user_id: $user_id}) DETACH DELETE f",
                user_id=user_id,
            )


# ── fact_id ───────────────────────────────────────────────────────────


def test_k11_7_fact_id_deterministic():
    a = fact_id("u-1", "p-1", "decision", "Use fire magic")
    b = fact_id("u-1", "p-1", "decision", "Use fire magic")
    assert a == b
    assert len(a) == 32


def test_k11_7_fact_id_canonicalizes_content():
    a = fact_id("u-1", "p-1", "decision", "Use fire magic")
    b = fact_id("u-1", "p-1", "decision", "  USE Fire MAGIC!  ")
    assert a == b


def test_k11_7_fact_id_distinct_per_type():
    a = fact_id("u-1", "p-1", "decision", "Use fire")
    b = fact_id("u-1", "p-1", "preference", "Use fire")
    assert a != b


def test_k11_7_fact_id_rejects_invalid_type():
    with pytest.raises(ValueError, match="type must be one of"):
        fact_id("u-1", "p-1", "decree", "x")


def test_k11_7_fact_id_rejects_empty_inputs():
    for kwargs in (
        dict(user_id="", project_id="p", type="decision", content="x"),
        dict(user_id="u", project_id="p", type="", content="x"),
        dict(user_id="u", project_id="p", type="decision", content=""),
    ):
        with pytest.raises(ValueError):
            fact_id(**kwargs)


def test_k11_7_fact_types_constant_matches_literal():
    assert set(FACT_TYPES) == {
        "decision",
        "preference",
        "milestone",
        "negation",
    }


# ── merge_fact ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_merge_fact_creates_node(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.85,
            source_chapter="ch-12",
        )
    assert f.user_id == test_user
    assert f.type == "decision"
    assert f.content == "Use fire magic"
    assert f.canonical_content == "use fire magic"
    assert f.confidence == 0.85
    assert f.source_chapter == "ch-12"
    assert f.valid_until is None
    assert f.pending_validation is False


@pytest.mark.asyncio
async def test_k11_7_merge_fact_is_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.5,
        )
        b = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="USE fire MAGIC",  # cosmetic diff
            confidence=0.5,
        )
    assert a.id == b.id
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (f:Fact {id: $id}) RETURN count(f) AS n", id=a.id
        )
        record = await result.single()
    assert record["n"] == 1


@pytest.mark.asyncio
async def test_k11_7_merge_fact_pass2_promotion(neo4j_driver, test_user):
    """Pass 1 quarantined fact (low conf, pending=true) → Pass 2
    LLM promotes (high conf, pending=false). The existing node
    upgrades in place."""
    async with neo4j_driver.session() as session:
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.4,
            pending_validation=True,
        )
        promoted = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.95,
            pending_validation=False,
        )
    assert promoted.confidence == 0.95
    assert promoted.pending_validation is False


@pytest.mark.asyncio
async def test_k11_7_merge_fact_validates_type():
    with pytest.raises(ValueError, match="type"):
        await merge_fact(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="bogus",
            content="x",
        )


@pytest.mark.asyncio
async def test_k11_7_merge_fact_validates_content():
    with pytest.raises(ValueError, match="content"):
        await merge_fact(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="decision",
            content="",
        )


# ── get_fact ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_get_fact_returns_none_when_missing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await get_fact(session, user_id=test_user, fact_id="0" * 32)
    assert result is None


@pytest.mark.asyncio
async def test_k11_7_get_fact_does_not_cross_user_boundary(neo4j_driver):
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            f = await merge_fact(
                session,
                user_id=user_a,
                project_id="p-1",
                type="decision",
                content="Secret",
            )
            from_b = await get_fact(
                session, user_id=user_b, fact_id=f.id
            )
        assert from_b is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (f:Fact) WHERE f.user_id IN [$ua, $ub] DETACH DELETE f",
                ua=user_a,
                ub=user_b,
            )


# ── list_facts_by_type ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_list_facts_filters_by_type(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="A decision",
            confidence=0.9,
        )
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="preference",
            content="A preference",
            confidence=0.9,
        )
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="milestone",
            content="A milestone",
            confidence=0.9,
        )
        decisions = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1", type="decision"
        )
        all_facts = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
    assert len(decisions) == 1
    assert decisions[0].content == "A decision"
    assert len(all_facts) == 3


@pytest.mark.asyncio
async def test_k11_7_list_facts_excludes_pending_by_default(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Quarantined",
            confidence=0.4,
            pending_validation=True,
        )
        excluded = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
        included = await list_facts_by_type(
            session,
            user_id=test_user,
            project_id="p-1",
            min_confidence=0.0,
            exclude_pending=False,
        )
    assert excluded == []
    assert len(included) == 1


@pytest.mark.asyncio
async def test_k11_7_list_facts_excludes_invalidated(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Will be invalidated",
            confidence=0.9,
        )
        before = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
        await invalidate_fact(session, user_id=test_user, fact_id=f.id)
        after = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
    assert len(before) == 1
    assert after == []


@pytest.mark.asyncio
async def test_k11_7_list_facts_validates_type():
    with pytest.raises(ValueError, match="type must be one of"):
        await list_facts_by_type(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="bogus",
        )


# ── invalidate_fact ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_invalidate_fact_sets_valid_until(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="X",
            confidence=0.9,
        )
        invalidated = await invalidate_fact(
            session, user_id=test_user, fact_id=f.id
        )
    assert invalidated is not None
    assert invalidated.valid_until is not None


@pytest.mark.asyncio
async def test_k11_7_invalidate_fact_returns_none_for_missing(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        result = await invalidate_fact(
            session, user_id=test_user, fact_id="0" * 32
        )
    assert result is None


# ── delete_facts_with_zero_evidence ───────────────────────────────────


# ── K11.7-R1 review-fix tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_r1_merge_fact_rejects_empty_source_type():
    """K11.7-R1/R3 fix."""
    with pytest.raises(ValueError, match="source_type"):
        await merge_fact(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="decision",
            content="Use fire",
            source_type="",
        )


@pytest.mark.asyncio
async def test_k11_7_r1_merge_fact_empty_source_chapter_normalized(
    neo4j_driver, test_user
):
    """K11.7-R1/R4 fix. Empty source_chapter normalizes to None
    so the stored value is NULL, not "" — keeps downstream
    chapter-id filters honest."""
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire",
            confidence=0.9,
            source_chapter="",
        )
    assert f.source_chapter is None


@pytest.mark.asyncio
async def test_k11_7_delete_facts_zero_evidence(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="A",
            confidence=0.9,
        )
        survivor = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Survivor",
            confidence=0.9,
        )
        await session.run(
            "MATCH (f:Fact {id: $id}) SET f.evidence_count = 1",
            id=survivor.id,
        )
        deleted = await delete_facts_with_zero_evidence(
            session, user_id=test_user, project_id="p-1"
        )
    assert deleted == 1
    async with neo4j_driver.session() as session:
        gone = await get_fact(session, user_id=test_user, fact_id=a.id)
        kept = await get_fact(
            session, user_id=test_user, fact_id=survivor.id
        )
    assert gone is None
    assert kept is not None
